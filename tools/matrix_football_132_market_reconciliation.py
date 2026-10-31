from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_prospective_market_freeze import build_freeze

ROOT = Path(".")
TARGET_DATE = "2026-10-06"
CYCLE_ID = "20261006T120503Z"
CYCLE_ROOT = ROOT / "evidence/api_football/prospective_daily" / TARGET_DATE / CYCLE_ID
OUT_ROOT = ROOT / "evidence/football_world_inventory" / TARGET_DATE / "canonical_132_market_reconciliation"
BOGOTA = ZoneInfo("America/Bogota")

LANE_BET_IDS = {
    "TEAM_TOTAL_SHOTS_HOME": {221},
    "TEAM_TOTAL_SHOTS_AWAY": {220},
    "TEAM_FOULS_TOTAL": {173},
    "PLAYER_SHOTS_V3": {240, 241, 265, 270, 276},
}
TEAM_LANE_DIRS = {
    "TEAM_TOTAL_SHOTS_HOME": "team_total_shots_home",
    "TEAM_TOTAL_SHOTS_AWAY": "team_total_shots_away",
    "TEAM_FOULS_TOTAL": "team_fouls_total",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _utc(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"NAIVE_TIMESTAMP:{value}")
    return dt.astimezone(timezone.utc)


def _sha_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _compact_offer(hit: dict[str, Any], observed_at: str, run_id: str) -> list[dict[str, Any]]:
    out = []
    for v in hit.get("values") or []:
        value = str(v.get("value") or "")
        line = None
        parts = value.split()
        if parts:
            try:
                line = float(parts[-1])
            except Exception:
                line = None
        odd = v.get("odd")
        try:
            odd_num = float(odd) if odd is not None else None
        except Exception:
            odd_num = None
        out.append(
            {
                "observed_at_utc": observed_at,
                "run_id": run_id,
                "bet_id": int(hit.get("bet_id") or 0),
                "bet_name": hit.get("bet_name"),
                "bookmaker_id": hit.get("bookmaker_id"),
                "bookmaker_name": hit.get("bookmaker_name"),
                "policy_reference_bookmaker": bool(hit.get("policy_reference_bookmaker")),
                "value": value,
                "line": line,
                "decimal_odd": odd_num,
            }
        )
    return out


def _fixture_probe_state() -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "odds_snapshot_count": 0,
            "lineup_snapshot_count": 0,
            "lineup_observed": False,
            "lineup_player_count_max": 0,
            "offers": defaultdict(list),
            "offer_snapshots": defaultdict(set),
            "seen_in_odds_probe": False,
            "seen_in_lineup_probe": False,
            "explicit_player_blockers": set(),
            "explicit_team_blockers": defaultdict(set),
        }
    )

    live_root = ROOT / "evidence/api_football/market_expansion/live_probe/runs"
    for manifest_path in sorted(live_root.glob("*/manifest.json")):
        m = _load(manifest_path)
        observed_at = m.get("observed_at_utc")
        if not observed_at:
            continue
        obs_dt = _utc(observed_at)
        run_id = str(m.get("run_id") or manifest_path.parent.name)

        for row in ((m.get("team_total_shots") or {}).get("rows") or []):
            fid = str(row.get("fixture_id") or "")
            kickoff = row.get("kickoff_utc")
            if not fid or not kickoff or obs_dt >= _utc(kickoff):
                continue
            s = state[fid]
            s["seen_in_odds_probe"] = True
            s["odds_snapshot_count"] += 1
            for hit in row.get("hits") or []:
                try:
                    bid = int(hit.get("bet_id"))
                except Exception:
                    continue
                for lane, ids in LANE_BET_IDS.items():
                    if bid in ids:
                        s["offer_snapshots"][lane].add(run_id)
                        s["offers"][lane].extend(_compact_offer(hit, str(observed_at), run_id))

        for row in ((m.get("player_shots") or {}).get("rows") or []):
            fid = str(row.get("fixture_id") or "")
            kickoff = row.get("kickoff_utc")
            if not fid or not kickoff or obs_dt >= _utc(kickoff):
                continue
            s = state[fid]
            s["seen_in_lineup_probe"] = True
            s["lineup_snapshot_count"] += 1
            lineup = row.get("lineup") or {}
            pc = int(lineup.get("player_count") or 0)
            tc = int(lineup.get("team_count") or 0)
            s["lineup_player_count_max"] = max(s["lineup_player_count_max"], pc)
            if tc >= 2 and pc > 0:
                s["lineup_observed"] = True

    player_root = ROOT / "evidence/api_football/player_shots_v3_prospective/runs"
    for manifest_path in sorted(player_root.glob("*/manifest.json")):
        m = _load(manifest_path)
        for b in m.get("blockers") or []:
            fid = str(b.get("fixture_id") or "")
            reason = str(b.get("reason") or "")
            if fid and reason:
                state[fid]["explicit_player_blockers"].add(reason)

    team_root = ROOT / "evidence/api_football/promoted_team_markets/runs"
    for manifest_path in sorted(team_root.glob("*/manifest.json")):
        m = _load(manifest_path)
        for b in m.get("blockers") or []:
            fid = str(b.get("fixture_id") or "")
            lane = str(b.get("lane") or "")
            reason = str(b.get("reason") or "")
            if fid and lane in TEAM_LANE_DIRS and reason:
                state[fid]["explicit_team_blockers"][lane].add(reason)

    return state


def _freeze_ledgers() -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    base = ROOT / "evidence/api_football/promoted_team_markets"
    for lane, d in TEAM_LANE_DIRS.items():
        by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _load_jsonl(base / d / "freeze_ledger.jsonl"):
            by_fixture[str(row.get("fixture_id") or "")].append(row)
        result[lane] = by_fixture

    by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _load_jsonl(ROOT / "evidence/api_football/player_shots_v3_prospective/freeze_ledger.jsonl"):
        by_fixture[str(row.get("fixture_id") or "")].append(row)
    result["PLAYER_SHOTS_V3"] = by_fixture
    return result


def _lane_summary(fid: str, lane: str, probe: dict[str, Any], ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    freezes = list(ledgers.get(lane, {}).get(fid, []))
    offers = list((probe.get("offers") or {}).get(lane, []))
    bookmakers = sorted({str(x.get("bookmaker_name")) for x in offers if x.get("bookmaker_name")})
    policy_bookmakers = sorted({str(x.get("bookmaker_name")) for x in offers if x.get("bookmaker_name") and x.get("policy_reference_bookmaker")})
    lines = sorted({float(x["line"]) for x in offers if x.get("line") is not None})
    offer_times = sorted({str(x.get("observed_at_utc")) for x in offers if x.get("observed_at_utc")})

    availability = "OFFER_OBSERVED" if offers else (
        "NO_TARGET_OFFER_OBSERVED_IN_CHECKED_SNAPSHOTS"
        if probe.get("seen_in_odds_probe")
        else "NOT_OBSERVED_IN_PERSISTED_PREMATCH_ODDS_PROBE"
    )

    reasons: list[str] = []
    state = "BLOCKED"
    if freezes:
        state = "YA_CONGELADO"
    elif lane == "PLAYER_SHOTS_V3":
        reasons.extend(sorted(probe.get("explicit_player_blockers") or []))
        if not probe.get("seen_in_lineup_probe"):
            reasons.append("NO_PERSISTED_PREMATCH_LINEUP_PROBE")
        elif not probe.get("lineup_observed"):
            reasons.append("PREMATCH_LINEUP_NOT_AVAILABLE")
        if not offers:
            reasons.append("NO_CANONICAL_PLAYER_SHOTS_OFFER_OBSERVED")
        if offers and not policy_bookmakers:
            reasons.append("ONLY_NON_POLICY_REFERENCE_OFFER_OBSERVED")
        if offers and probe.get("lineup_observed") and not reasons:
            reasons.append("NO_GOVERNED_FREEZE_PERSISTED")
    else:
        reasons.extend(sorted((probe.get("explicit_team_blockers") or {}).get(lane, [])))
        if not probe.get("seen_in_odds_probe"):
            reasons.append("NO_PERSISTED_PREMATCH_ODDS_PROBE")
        elif not offers:
            reasons.append("NO_CANONICAL_TARGET_OFFER_OBSERVED")
        if offers and not policy_bookmakers:
            reasons.append("ONLY_NON_POLICY_REFERENCE_OFFER_OBSERVED")
        if offers and not reasons and policy_bookmakers:
            reasons.append("NO_GOVERNED_FREEZE_PERSISTED")

    if not reasons and not freezes:
        reasons.append("NO_GOVERNED_FREEZE_PERSISTED")

    freeze_detail = [
        {
            "freeze_at_utc": fr.get("freeze_at_utc"),
            "kickoff_utc": fr.get("kickoff_utc"),
            "market_line": fr.get("market_line"),
            "bookmaker_name": fr.get("bookmaker_name"),
            "over_odds_observed": fr.get("over_odds_observed"),
            "under_odds_observed": fr.get("under_odds_observed"),
            "frozen_probability_over": fr.get("frozen_probability_over"),
            "odds_used_to_generate_probability": fr.get("odds_used_to_generate_probability"),
            "real_money": fr.get("real_money"),
            "player_id": fr.get("player_id"),
            "player_name": fr.get("player_name"),
        }
        for fr in freezes
    ]

    return {
        "governance_state": state,
        "availability_real": availability,
        "prematch_odds_probe_seen": bool(probe.get("seen_in_odds_probe")),
        "prematch_odds_snapshot_count": int(probe.get("odds_snapshot_count") or 0),
        "offer_snapshot_count": len((probe.get("offer_snapshots") or {}).get(lane, set())),
        "offer_observation_count": len(offers),
        "bookmakers_observed": bookmakers,
        "policy_reference_bookmakers_observed": policy_bookmakers,
        "market_lines_observed": lines,
        "first_offer_observed_at_utc": offer_times[0] if offer_times else None,
        "last_offer_observed_at_utc": offer_times[-1] if offer_times else None,
        "lineup_probe_seen": bool(probe.get("seen_in_lineup_probe")) if lane == "PLAYER_SHOTS_V3" else None,
        "lineup_observed": bool(probe.get("lineup_observed")) if lane == "PLAYER_SHOTS_V3" else None,
        "lineup_player_count_max": int(probe.get("lineup_player_count_max") or 0) if lane == "PLAYER_SHOTS_V3" else None,
        "block_reasons": sorted(set(reasons)),
        "freeze_count": len(freezes),
        "freeze_detail": freeze_detail,
        "evidence_note": "NOT_OBSERVED does not prove the market was unavailable elsewhere; it means no persisted prematch API-Football probe observed it.",
    }


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    cycle_summary = _load(CYCLE_ROOT / "cycle_summary.json")
    canonical, canonical_manifest = load_chunked_canonical_bundle(CYCLE_ROOT / "canonical_analysis")
    ready_rows = list(canonical.get("inputs") or [])
    if len(ready_rows) != 138 or int(canonical_manifest["ready_input_count"]) != 138:
        raise SystemExit("CANONICAL_READY_COUNT_NOT_138")

    global_freeze_path = ROOT / "evidence/api_football/prospective_market_freeze/freeze.json"
    global_freeze = _load(global_freeze_path)
    global_rows = list(global_freeze.get("rows") or [])
    global_by_id = {str(r.get("fixture_id") or ""): r for r in global_rows}
    if len(global_by_id) != len(global_rows):
        raise SystemExit("GLOBAL_FREEZE_DUPLICATE_FIXTURE_ID")

    new_ids = {str(x) for x in cycle_summary["freeze"]["new_fixture_ids"]}
    if len(new_ids) != 14:
        raise SystemExit("CYCLE_NEW_FREEZE_COUNT_NOT_14")
    new_freeze_times = {str(global_by_id[fid]["freeze_at_utc"]) for fid in new_ids if fid in global_by_id}
    if len(new_freeze_times) != 1:
        raise SystemExit(f"NEW_FREEZE_TIME_NOT_UNIQUE:{sorted(new_freeze_times)}")
    cycle_freeze_at = _utc(next(iter(new_freeze_times)))

    rebuilt = build_freeze(
        ROOT,
        cycle_freeze_at,
        canonical_root=CYCLE_ROOT / "canonical_analysis",
        history_root=CYCLE_ROOT / "history",
    )
    candidate_rows = list(rebuilt.get("rows") or [])
    exclusions = list(rebuilt.get("exclusions") or [])
    if len(candidate_rows) != 132:
        raise SystemExit(f"REBUILT_CANDIDATE_COUNT_NOT_132:{len(candidate_rows)}")
    if len(exclusions) != 6:
        raise SystemExit(f"REBUILT_EXCLUSION_COUNT_NOT_6:{len(exclusions)}")

    candidate_ids = {str(r["fixture_id"]) for r in candidate_rows}
    if len(candidate_ids) != 132:
        raise SystemExit("CANDIDATE_IDS_NOT_UNIQUE")
    if not new_ids.issubset(candidate_ids):
        raise SystemExit("NEW_IDS_NOT_SUBSET_OF_CANDIDATES")
    existing_ids = candidate_ids - new_ids
    if len(existing_ids) != 118:
        raise SystemExit(f"EXISTING_ID_COUNT_NOT_118:{len(existing_ids)}")
    if any(fid not in global_by_id for fid in candidate_ids):
        raise SystemExit("CANDIDATE_NOT_IN_GLOBAL_FREEZE")

    probes = _fixture_probe_state()
    ledgers = _freeze_ledgers()
    rows = []

    for fid in sorted(candidate_ids, key=lambda x: (_utc(global_by_id[x]["kickoff_utc"]), int(x))):
        fr = global_by_id[fid]
        p = fr.get("frozen_research_probabilities") or {}
        p1 = p.get("1x2") or {}
        po = p.get("over_2_5")
        if po is None or not all(k in p1 for k in ("H", "D", "A")):
            raise SystemExit(f"CORE_PROBABILITY_MISSING:{fid}")
        if abs(sum(float(p1[k]) for k in ("H", "D", "A")) - 1.0) > 1e-8:
            raise SystemExit(f"1X2_NOT_NORMALIZED:{fid}")

        probe = probes.get(fid, {})
        kickoff = _utc(fr["kickoff_utc"])
        rows.append({
            "fixture_id": fid,
            "competition_id": fr.get("competition_id"),
            "competition_name": fr.get("competition_name"),
            "home_team_id": fr.get("home_team_id"),
            "home_team_name": fr.get("home_team_name"),
            "away_team_id": fr.get("away_team_id"),
            "away_team_name": fr.get("away_team_name"),
            "kickoff_utc": kickoff.isoformat(),
            "kickoff_bogota": kickoff.astimezone(BOGOTA).isoformat(),
            "cycle_status": "PROCESABLE" if fid in new_ids else "YA_CONGELADO",
            "current_core_status": "YA_CONGELADO",
            "core_freeze_at_utc": fr.get("freeze_at_utc"),
            "core_markets": {
                "OVER_2_5": {
                    "status": (fr.get("market_status") or {}).get("over_2_5"),
                    "frozen_probability": float(po),
                },
                "1X2": {
                    "status": (fr.get("market_status") or {}).get("1x2"),
                    "frozen_probabilities": {
                        "HOME": float(p1["H"]),
                        "DRAW": float(p1["D"]),
                        "AWAY": float(p1["A"]),
                    },
                },
            },
            "developing_markets": {
                "PLAYER_SHOTS_V3": _lane_summary(fid, "PLAYER_SHOTS_V3", probe, ledgers),
                "TEAM_TOTAL_SHOTS_HOME": _lane_summary(fid, "TEAM_TOTAL_SHOTS_HOME", probe, ledgers),
                "TEAM_TOTAL_SHOTS_AWAY": _lane_summary(fid, "TEAM_TOTAL_SHOTS_AWAY", probe, ledgers),
                "TEAM_FOULS_TOTAL": _lane_summary(fid, "TEAM_FOULS_TOTAL", probe, ledgers),
            },
            "protections": {
                "odds_used_to_generate_core_probability": bool(fr.get("odds_used_to_generate_probability")),
                "p_matrix": fr.get("p_matrix"),
                "real_money": "BLOCKED",
            },
        })

    if len(rows) != 132 or len({r["fixture_id"] for r in rows}) != 132:
        raise SystemExit("OUTPUT_ROWS_NOT_132_UNIQUE")
    status_counts = Counter(r["cycle_status"] for r in rows)
    if status_counts != Counter({"YA_CONGELADO": 118, "PROCESABLE": 14}):
        raise SystemExit(f"CYCLE_STATUS_COUNTS_BAD:{status_counts}")
    if any(r["protections"]["odds_used_to_generate_core_probability"] for r in rows):
        raise SystemExit("ODDS_TO_CORE_PROBABILITY_DETECTED")
    if any(r["protections"]["p_matrix"] is not None for r in rows):
        raise SystemExit("P_MATRIX_UNEXPECTED")

    ready_by_id = {str(x["fixture_id"]): x for x in ready_rows}
    blocked_ready = []
    for ex in sorted(exclusions, key=lambda x: int(x["fixture_id"])):
        fid = str(ex["fixture_id"])
        raw = ready_by_id.get(fid) or {}
        blocked_ready.append({
            "fixture_id": fid,
            "home_team_name": raw.get("home_team_name"),
            "away_team_name": raw.get("away_team_name"),
            "competition_name": raw.get("competition_name"),
            "kickoff_utc": raw.get("kickoff_utc"),
            "status": "BLOCKED",
            "reason": ex.get("reason"),
            "required_source": ex.get("required_source"),
        })

    jsonl_path = OUT_ROOT / "MATRIX_CANONICAL_132_MARKET_RECONCILIATION.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    blocked_path = OUT_ROOT / "MATRIX_PIT_READY_BLOCKED_6.json"
    blocked_path.write_text(json.dumps(blocked_ready, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lane_counts = {lane: dict(Counter(r["developing_markets"][lane]["governance_state"] for r in rows)) for lane in LANE_BET_IDS}
    availability_counts = {lane: dict(Counter(r["developing_markets"][lane]["availability_real"] for r in rows)) for lane in LANE_BET_IDS}
    offer_examples = {}
    for lane in LANE_BET_IDS:
        offer_examples[lane] = [
            {
                "fixture_id": r["fixture_id"],
                "match": f'{r["home_team_name"]} - {r["away_team_name"]}',
                "bookmakers": r["developing_markets"][lane]["bookmakers_observed"],
                "policy_reference_bookmakers": r["developing_markets"][lane]["policy_reference_bookmakers_observed"],
                "lines": r["developing_markets"][lane]["market_lines_observed"],
                "governance_state": r["developing_markets"][lane]["governance_state"],
                "block_reasons": r["developing_markets"][lane]["block_reasons"],
            }
            for r in rows if r["developing_markets"][lane]["availability_real"] == "OFFER_OBSERVED"
        ]

    summary = {
        "schema": "MATRIX_FOOTBALL_CANONICAL_132_MARKET_RECONCILIATION_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_date_bogota": TARGET_DATE,
        "cycle_id": CYCLE_ID,
        "cycle_freeze_at_utc": cycle_freeze_at.isoformat(),
        "source_cycle_summary": (CYCLE_ROOT / "cycle_summary.json").as_posix(),
        "source_canonical_bundle_sha256": canonical_manifest["bundle_sha256"],
        "source_global_freeze_sha256": _sha_bytes(global_freeze_path.read_bytes()),
        "counts": {
            "future_fixtures_received": int(cycle_summary["fixture_capture"]["fixtures_received"]),
            "eligible_future_fixtures": int(cycle_summary["fixture_capture"]["eligible_future_fixtures"]),
            "pit_ready": 138,
            "governed_freeze_candidates": 132,
            "cycle_procesable_new_freezes": 14,
            "cycle_ya_congelado": 118,
            "pit_ready_blocked_before_freeze": 6,
            "physical_collision_blocked": int(cycle_summary["freeze"]["physical_collision_blocked_count"]),
        },
        "core_markets": {
            "OVER_2_5": "132/132 have immutable frozen probability rows",
            "1X2": "132/132 have immutable frozen probability rows",
        },
        "developing_governance_state_counts": lane_counts,
        "developing_real_availability_counts": availability_counts,
        "developing_offer_examples": offer_examples,
        "blocked_ready_6": blocked_ready,
        "truth_rules": {
            "not_observed_is_not_equal_to_unavailable": True,
            "offer_observed_requires_persisted_prematch_snapshot": True,
            "name_only_binding_prohibited": True,
            "no_backfill": True,
            "missing_not_zero": True,
            "odds_to_p_matrix": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "integrity": {
            "canonical_ready_count_138": True,
            "rebuilt_candidate_count_132": True,
            "new_plus_existing_equals_132": True,
            "new_count_14": True,
            "existing_count_118": True,
            "blocked_count_6": True,
            "output_unique_fixture_ids_132": True,
            "odds_used_to_generate_core_probability": False,
            "p_matrix_generated": False,
            "status": "PASS",
        },
    }
    summary_path = OUT_ROOT / "MATRIX_CANONICAL_132_MARKET_RECONCILIATION_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# MATRIX Football — 132 canónicos por partido (06-OCT-2026)",
        "",
        "## Control físico",
        "",
        "- PIT-ready: **138**.",
        "- Candidatos gobernados de freeze reconstruidos: **132**.",
        "- PROCESABLE en el ciclo (freezes nuevos): **14**.",
        "- YA CONGELADO antes del ciclo: **118**.",
        "- BLOCKED entre PIT-ready antes del freeze: **6** (anexo separado).",
        f"- Colisiones físicas: **{cycle_summary['freeze']['physical_collision_blocked_count']}**.",
        "- Integridad: **PASS**.",
        "",
        "## Lectura de estados",
        "",
        "- PROCESABLE: entró como freeze nuevo en este ciclo.",
        "- YA_CONGELADO: ya existía en el freeze inmutable y fue saltado sin mutarlo.",
        "- En mercados DEVELOPING, BLOCKED significa que no existe un freeze gobernado para esa lane; la causa queda registrada.",
        "- NOT_OBSERVED_IN_PERSISTED_PREMATCH_ODDS_PROBE no significa que el mercado no existiera en otra casa; significa que no quedó capturado en los snapshots prematch persistidos.",
        "",
        "## Listado 132",
        "",
        "| # | Fixture | Partido | Kickoff Bogotá | Estado ciclo | P Over2.5 | P 1 | P X | P 2 | Player Shots v3 | Shots H | Shots A | Fouls |",
        "|---:|---:|---|---|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        core = r["core_markets"]
        dev = r["developing_markets"]
        def short(lane: str) -> str:
            d = dev[lane]
            if d["governance_state"] == "YA_CONGELADO":
                return "YA CONGELADO"
            if d["availability_real"] == "OFFER_OBSERVED":
                return "BLOCKED (oferta observada)"
            if d["availability_real"] == "NO_TARGET_OFFER_OBSERVED_IN_CHECKED_SNAPSHOTS":
                return "BLOCKED (sin oferta en probe)"
            return "BLOCKED (sin evidencia prematch)"
        md_lines.append(
            f'| {i} | {r["fixture_id"]} | {r["home_team_name"]} - {r["away_team_name"]} | '
            f'{r["kickoff_bogota"]} | {r["cycle_status"]} | '
            f'{core["OVER_2_5"]["frozen_probability"]:.4f} | '
            f'{core["1X2"]["frozen_probabilities"]["HOME"]:.4f} | '
            f'{core["1X2"]["frozen_probabilities"]["DRAW"]:.4f} | '
            f'{core["1X2"]["frozen_probabilities"]["AWAY"]:.4f} | '
            f'{short("PLAYER_SHOTS_V3")} | {short("TEAM_TOTAL_SHOTS_HOME")} | '
            f'{short("TEAM_TOTAL_SHOTS_AWAY")} | {short("TEAM_FOULS_TOTAL")} |'
        )

    md_lines += ["", "## 6 PIT-ready bloqueados antes del freeze", "", "| Fixture | Partido | Causa |", "|---:|---|---|"]
    for r in blocked_ready:
        md_lines.append(f'| {r["fixture_id"]} | {r["home_team_name"]} - {r["away_team_name"]} | {r["reason"]} |')
    md_lines += [
        "",
        "## Disponibilidad real de mercados DEVELOPING",
        "",
        "Los conteos exactos están en el JSON de resumen. Las líneas/bookmakers observados y los motivos por fixture están en el JSONL de 132 filas.",
        "",
        "**Gobernanza:** no backfill, Missing ≠ 0, sin imputación silenciosa, no odds→P_MATRIX, automatic_wagering=false, REAL_MONEY=BLOCKED.",
        "",
    ]
    md_path = OUT_ROOT / "MATRIX_CANONICAL_132_MARKET_RECONCILIATION.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    manifest = {
        "schema": "MATRIX_FOOTBALL_CANONICAL_132_MARKET_RECONCILIATION_MANIFEST_V1",
        "generated_at_utc": summary["generated_at_utc"],
        "status": "PASS",
        "files": {},
        "row_count": 132,
        "unique_fixture_count": 132,
        "cycle_status_counts": dict(status_counts),
        "blocked_ready_count": 6,
        "real_money": "BLOCKED",
    }
    for p in (jsonl_path, blocked_path, summary_path, md_path):
        data = p.read_bytes()
        manifest["files"][p.name] = {"bytes": len(data), "sha256": _sha_bytes(data)}
    (OUT_ROOT / "MANIFEST_SHA256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "rows": 132,
        "procesable": 14,
        "ya_congelado": 118,
        "blocked_ready": 6,
        "lane_counts": lane_counts,
        "availability_counts": availability_counts,
        "out_root": OUT_ROOT.as_posix(),
        "real_money": "BLOCKED",
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
