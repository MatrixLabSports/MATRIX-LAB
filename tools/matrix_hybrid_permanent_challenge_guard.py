"""Fail-closed, permanent MATRIX Hybrid Elite challenge continuity guard.

Read-only source verification: counts, provenance, risk, and required lanes.
NEVER promotes a research probability, updates calibration or sends a bet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = Path("docs/MATRIX_RETO_CONTRATO_PERMANENTE_HIBRIDA_V1.md")
PAIR = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json")
MARKETS = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
TENNIS = Path("evidence/tennis/MATRIX_TENNIS_THREE_BLOCK_STAGNATION_AUDIT_LAST.json")
OOS = Path("evidence/football_world_inventory/MATRIX_FREE_POISSON_OOS_SCORECARD_LAST.json")
BAYES = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_FREE_BAYESIAN_LAST.json")
PAIR_WORKFLOW = Path(".github/workflows/matrix-hybrid-elite-research-pair-integration.yml")
HISTORY_WORKFLOW = Path(".github/workflows/matrix-independent-d2-authentic-prospective-recovery.yml")
EVALUATION_WORKFLOW = Path(".github/workflows/matrix-independent-free-poisson-oos.yml")
BAYES_WORKFLOW = Path(".github/workflows/matrix-hybrid-free-bayesian-prematch-research.yml")
THREE_WORKFLOW = Path(".github/workflows/matrix-hybrid-three-model-prospective-oos.yml")
TEAM_V2_WORKFLOW = Path(".github/workflows/matrix-hybrid-team-venue-beta-v2-prematch.yml")
FOUR_WORKFLOW = Path(".github/workflows/matrix-hybrid-four-model-prospective-oos.yml")
THREE_REPORT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_THREE_MODEL_OOS_LAST.json")
TEAM_V2_REPORT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_TEAM_VENUE_BETA_V2_LAST.json")
FOUR_REPORT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_FOUR_MODEL_OOS_LAST.json")
DUAL_SOURCE_LINEAGE = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_ORIGINAL_DUAL_FREEZE_LINEAGE_LAST.json")
BAYES_V1_DIAGNOSTIC = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_BAYESIAN_LEAGUE_BASELINE_DIAGNOSTIC_20261119.json")
PERMANENT_MODULES = (
    Path("tools/matrix_hybrid_elite_lab.py"),
    Path("tools/matrix_hybrid_elite_bayesian_shadow.py"),
    Path("tools/matrix_hybrid_elite_research_pair_bridge.py"),
    Path("tools/matrix_hybrid_free_bayesian_v1.py"),
    Path("tools/matrix_hybrid_three_model_research_oos.py"),
    Path("tools/matrix_hybrid_team_venue_beta_v2.py"),
    Path("tools/matrix_hybrid_original_dual_freeze_lineage.py"),
    Path("tools/matrix_hybrid_four_model_research_oos.py"),
)

REQUIRED_LANES = ("FOOTBALL_OVER25", "TENNIS_CHALLENGER_HARD",
                  "TENNIS_CHALLENGER_CLAY", "TENNIS_LIVE")
SCHEMA = "MATRIX_HYBRID_PERMANENT_CHALLENGE_GUARD_V1"
SOURCE_ORDER = ("SOFASCORE", "FLASHSCORE")


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_bytes())
    if not isinstance(obj, dict):
        raise ValueError("SOURCE_NOT_JSON_OBJECT")
    return obj


def utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("MISSING_CLOCK_TIMEZONE")
    return d.astimezone(timezone.utc)


def inspect(root: Path) -> dict:
    """Snapshot authentic local evidence without advancing any admission gates."""
    now = datetime.now(timezone.utc)
    sources = {}
    issues = []
    def doc(rel):
        path = root / rel
        if not path.is_file():
            issues.append("MISSING_SOURCE:" + rel.as_posix())
            return None
        try:
            data = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            issues.append("INVALID_SOURCE:" + rel.as_posix())
            return None
        sources[rel.as_posix()] = fingerprint(path)
        return data

    contract_path = root / CONTRACT
    if not contract_path.is_file():
        issues.append("MISSING_HYBRID_PERMANENT_CONTRACT")
    else:
        text = contract_path.read_text(encoding="utf-8")
        sources[CONTRACT.as_posix()] = fingerprint(contract_path)
        for phrase in ("SofaScore", "Flashscore", "Challenger Hard",
                       "Challenger Clay", "Live Tennis", "42 mercados",
                       "REAL_MONEY=BLOCKED", "automatic_wagering=false"):
            if phrase not in text:
                issues.append("CONTRACT_CLAUSE_MISSING:" + phrase)

    for module in PERMANENT_MODULES:
        p = root / module
        if not p.is_file():
            issues.append("MISSING_PERMANENT_HYBRID_MODEL:" + module.as_posix())
        else:
            sources[module.as_posix()] = fingerprint(p)

    scheduled = {}
    for label, rel in (("hybrid_pairs", PAIR_WORKFLOW),
                       ("free_D2", HISTORY_WORKFLOW),
                       ("independent_OOS", EVALUATION_WORKFLOW),
                       ("bayesian_prospective", BAYES_WORKFLOW),
                       ("three_model_prospective_oos", THREE_WORKFLOW),
                       ("team_aware_bayesian_v2", TEAM_V2_WORKFLOW),
                       ("four_model_prospective_oos", FOUR_WORKFLOW)):
        p = root / rel
        if not p.is_file():
            issues.append("MISSING_SCHEDULED_WORKFLOW:" + label)
            scheduled[label] = False
            continue
        raw = p.read_text(encoding="utf-8")
        sources[rel.as_posix()] = fingerprint(p)
        ok = (("schedule:" in raw) and
              ("ref: repair/cor09-world-pipeline" in raw) and
              ("BLOCKED" in raw) and
              ("on:" in raw))
        if not ok:
            issues.append("SCHEDULED_WORKFLOW_INCOMPLETE:" + label)
        scheduled[label] = ok

    market = doc(MARKETS)
    total, football, tennis = None, None, None
    counts = {}
    if market:
        total, football, tennis = (market.get("total_lanes"),
                                  market.get("football_lanes"),
                                  market.get("tennis_lanes"))
        counts = market.get("counts") or {}
        if (market.get("schema") != "MATRIX_42_LANE_PROSPECTIVE_REGISTRY_V1"
            or total != 42 or football != 30 or tennis != 12):
            issues.append("MARKET_SCOPE_OR_SCHEMA_NOT_42")
        if market.get("protections") is None:
            issues.append("MARKET_RISK_GOVERNANCE_NOT_PRESENT")
    tennis_doc = doc(TENNIS)
    tennis_counts = {}
    if tennis_doc:
        blocks = tennis_doc.get("blocks") or {}
        for lane, key in (("TENNIS_CHALLENGER_HARD", "hard"),
                          ("TENNIS_CHALLENGER_CLAY", "clay"),
                          ("TENNIS_LIVE", "live")):
            value = blocks.get(key)
            if not isinstance(value, dict) or type(value.get("current_counter")) is not int:
                issues.append("TENNIS_LANE_COUNTER_MISSING:" + lane)
            else:
                tennis_counts[lane] = value["current_counter"]
        order = [str(z).upper() for z in tennis_doc.get("source_order", [])]
        if tuple(order[:2]) != SOURCE_ORDER:
            issues.append("TENNIS_SOURCE_ORDER_NOT_BROWSER_FIRST")

    paired = doc(PAIR)
    pair_count = 0
    if paired:
        order = paired.get("source_order")
        if (paired.get("schema") != "MATRIX_HYBRID_ELITE_RESEARCH_PRELABEL_PAIRS_V1"
            or not isinstance(order, list)
            or tuple(str(x).upper() for x in order[:2]) != SOURCE_ORDER):
            issues.append("HYBRID_PAIR_SCHEMA_OR_SOURCE_ORDER")
        for name, expected in (("automatic_model_promotion", False),
                               ("original_model_parameters_mutated", False),
                               ("production_p_matrix_authorized", False),
                               ("telegram_signal_authorized", False),
                               ("automatic_wagering", False),
                               ("real_money", "BLOCKED"),
                               ("formal_hybrid_elite_lab_rows_admitted", 0),
                               ("existing_official_original_p_matrix_pairs", 0)):
            if paired.get(name) != expected:
                issues.append("UNAUTHORIZED_HYBRID_PROMOTION:" + name)
        rows = paired.get("prelabel_research_pairs")
        if not isinstance(rows, list):
            issues.append("HYBRID_PAIR_ROWS_NOT_LIST")
            rows = []
        pair_count = len(rows)
        if pair_count != paired.get("recovered_research_pair_count"):
            issues.append("HYBRID_PAIR_COUNT_MISMATCH")
        if paired.get("rejected_research_pair_count") != 0:
            issues.append("HYBRID_PAIR_INTEGRITY_REJECTIONS_PRESENT")
        ids = set()
        for row in rows:
            try:
                fid = str(row["physical_event_id"])
                if fid in ids:
                    raise ValueError("DUPLICATE_EVENT")
                ids.add(fid)
                kickoff = utc(row["event_start_at_utc"])
                if not (utc(row["original_formula_research_frozen_at_utc"]) < kickoff
                        and utc(row["independent_poisson_frozen_at_utc"]) < kickoff):
                    raise ValueError("FORECAST_AFTER_KICKOFF")
                if row.get("formal_hybrid_lab_admission_authorized") is not False:
                    raise ValueError("ILLEGAL_FORMAL_HYBRID_ADMISSION")
                for name, src, sha in (("original", row["original_freeze_path"],
                                       row["original_freeze_sha256"]),
                                       ("poisson", row["poisson_freeze_path"],
                                        row["poisson_freeze_sha256"])):
                    p = Path(src)
                    if p.is_absolute() or ".." in p.parts:
                        raise ValueError("UNSAFE_PATH_" + name)
                    source_path = root / p
                    if not source_path.is_file() or fingerprint(source_path) != sha:
                        raise ValueError("PHYSICAL_FREEZE_SHA_MISMATCH_" + name)
                a, b = (row["original_formula_research_p"],
                        row["independent_free_poisson_p"])
                if (type(a) not in (float, int) or type(b) not in (float, int)
                    or not math.isfinite(a) or not math.isfinite(b)
                    or not (0 < a < 1 and 0 < b < 1)):
                    raise ValueError("INVALID_RESEARCH_PROBABILITY")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                issues.append("HYBRID_PAIR_NOT_PHYSICALLY_VERIFIED:" + str(exc)[:90])
                break

    scorecard = doc(OOS)
    oos = {"prospective_pending": None, "settled_pairs": None,
           "rejected": None}
    if scorecard:
        for name, expected in (("production_p_matrix_authorized", False),
                               ("telegram_signal_authorized", False),
                               ("automatic_wagering", False),
                               ("real_money", "BLOCKED")):
            if scorecard.get(name) != expected:
                issues.append("OOS_UNAUTHORIZED_PROMOTION:" + name)
        if scorecard.get("schema") != "MATRIX_FREE_POISSON_POSTMATCH_PROSPECTIVE_SCORECARD_V1":
            issues.append("OOS_SCHEMA_MISMATCH")
        oos = {
            "prospective_pending": scorecard.get("future_forecasts_pending"),
            "settled_pairs": scorecard.get("independently_verified_settled_pairs"),
            "rejected": len(scorecard.get("rejected_forecasts_or_settlements") or []),
        }

    bayesian = None
    bayes_file = root / BAYES
    if bayes_file.is_file():
        b = doc(BAYES)
        if b:
            bayesian = {"research_forecasts": b.get("scored_count"),
                        "rejected": b.get("blocked_count")}
            for name, expected in (("automatic_model_promotion", False),
                                   ("telegram_signal_authorized", False),
                                   ("automatic_wagering", False),
                                   ("real_money", "BLOCKED")):
                if b.get(name) != expected:
                    issues.append("BAYESIAN_ILLEGAL_PROMOTION:" + name)

    baseline = doc(BAYES_V1_DIAGNOSTIC)
    if baseline:
        if (baseline.get("schema") !=
                "MATRIX_HYBRID_BAYESIAN_LEAGUE_BASELINE_DIAGNOSTIC_V1"
            or baseline.get("total_physical_paired_events") != 37
            or baseline.get("findings", {}).get(
                "competitions_with_constant_bayesian_v1_probability") != 6
            or baseline.get("no_model_promotion") is not True):
            issues.append("BAYESIAN_V1_DIAGNOSTIC_MISSING_OR_CHANGED")

    triple = {"state": "PENDING_FIRST_VERIFIED_CYCLE"}
    if (root / THREE_REPORT).is_file():
        t = doc(THREE_REPORT)
        if t:
            triple = {
                "state": t.get("status"),
                "physically_settled_comparisons":
                    t.get("three_model_authenticated_settled_count"),
                "pending_futures": t.get("three_model_pending_fixture_count"),
                "missing_bayesian_forecast_count":
                    len(t.get("three_model_missing_bayesian_forecasts") or []),
                "rejected": len(t.get("three_model_rejected") or []),
            }
            if (t.get("schema") !=
                    "MATRIX_HYBRID_THREE_MODEL_PROSPECTIVE_RESEARCH_OOS_V1"
                or t.get("model_winner_authorized") is not False
                or t.get("original_official_p_matrix_present") is not False
                or t.get("telegram_signal_authorized") is not False
                or t.get("automatic_wagering") is not False
                or t.get("real_money") != "BLOCKED"):
                issues.append("THREE_MODEL_OOS_PROVENANCE_OR_GOVERNANCE_INVALID")

    team_v2 = {"state": "PENDING_FIRST_VERIFIED_CYCLE"}
    if (root / TEAM_V2_REPORT).is_file():
        v = doc(TEAM_V2_REPORT)
        if v:
            team_v2 = {
                "state": "RESEARCH_ONLY",
                "new_forecasts": v.get("new_forecast_count"),
                "existing_forecasts": v.get("existing_forecast_count"),
                "blocked": v.get("blocked_count"),
                "expired_unfrozen": v.get("expired_unfrozen_count"),
                "unique_p_per_league":
                    v.get("competition_unique_prediction_counts"),
            }
            if (v.get("schema") !=
                    "MATRIX_HYBRID_TEAM_VENUE_BETA_V2_RESEARCH_CYCLE_V1"
                or v.get("scientific_improvement_certified") is not False
                or v.get("original_parameters_mutated") is not False
                or v.get("automatic_model_promotion") is not False
                or v.get("telegram_signal_authorized") is not False
                or v.get("automatic_wagering") is not False
                or v.get("real_money") != "BLOCKED"):
                issues.append("TEAM_VENUE_V2_PROVENANCE_OR_GOVERNANCE_INVALID")

    dual = doc(DUAL_SOURCE_LINEAGE)
    original_dual_freeze = {"state": "UNVERIFIED"}
    if dual:
        original_dual_freeze = {
            "state": dual.get("status"),
            "unique_physical_events": dual.get("physical_fixture_count"),
            "matched": dual.get("lineage_matched_fixture_count"),
            "two_forecast_snapshots_per_event":
                dual.get("two_snapshot_fixture_count"),
            "exactly_two_snapshot_events":
                dual.get("exactly_two_snapshot_fixture_count"),
            "more_than_two_snapshot_events":
                dual.get("more_than_two_snapshot_fixture_count"),
            "additional_snapshot_files_excluded":
                dual.get("additional_snapshot_files_excluded_from_observations"),
            "later_changed_history_sha_snapshots":
                dual.get("later_snapshots_with_changed_history_sha256"),
            "later_changed_probability_snapshots":
                dual.get("later_snapshots_with_changed_probability"),
            "rejected": dual.get("lineage_rejected_fixture_count"),
        }
        if (dual.get("schema") !=
                "MATRIX_HYBRID_ORIGINAL_DUAL_FREEZE_LINEAGE_V1"
            or dual.get("lineage_rejected_fixture_count") != 0
            or dual.get("lineage_matched_fixture_count") !=
               dual.get("physical_fixture_count")
            or dual.get("two_snapshot_fixture_count", 0) < 37
            or dual.get("telegram_signal_authorized") is not False
            or dual.get("real_money") != "BLOCKED"):
            issues.append("INVALID_PRIMARY_VS_SECONDARY_FORMULA_SHA_LINEAGE")
        exactly = dual.get("exactly_two_snapshot_fixture_count")
        multiple = dual.get("more_than_two_snapshot_fixture_count")
        extras = dual.get("additional_snapshot_files_excluded_from_observations")
        later_history = dual.get("later_snapshots_with_changed_history_sha256")
        later_probability = dual.get("later_snapshots_with_changed_probability")
        if (not all(type(v) is int and v >= 0 for v in
                    (exactly, multiple, extras, later_history, later_probability))
            or exactly + multiple != dual.get("lineage_matched_fixture_count")
            or extras < multiple
            or later_history > extras + multiple
            or later_probability > extras + multiple):
            issues.append("HYBRID_EXTRA_FROZEN_SNAPSHOT_ACCOUNTING_INVALID")

    four = {"state": "PENDING_FIRST_VERIFIED_CYCLE"}
    if (root / FOUR_REPORT).is_file():
        doc4 = doc(FOUR_REPORT)
        if doc4:
            four = {
                "state": doc4.get("status"),
                "frozen_future_events": doc4.get("four_model_frozen_future_count"),
                "verified_settlements": doc4.get("four_model_verified_settled_count"),
                "rejected": len(doc4.get("four_model_rejected") or []),
                "v2_unfrozen": len(doc4.get("four_model_missing_v2_forecasts") or []),
            }
            if (doc4.get("schema") != "MATRIX_HYBRID_FOUR_MODEL_RESEARCH_OOS_V1"
                or doc4.get("model_superiority_claim_authorized") is not False
                or doc4.get("original_p_matrix_official_probability_present") is not False
                or doc4.get("automatic_model_promotion") is not False
                or doc4.get("telegram_signal_authorized") is not False
                or doc4.get("automatic_wagering") is not False
                or doc4.get("real_money") != "BLOCKED"):
                issues.append("FOUR_WAY_OOS_GOVERNANCE_OR_SCHEMA_INVALID")

    # Absence of proven per-sport original p_MATRIX pairs is BLOCKED, not a
    # software failure; a good cron run must never be presented as model GO.
    return {
        "schema": SCHEMA,
        "checked_at_utc": now.isoformat(),
        "contract": CONTRACT.as_posix(),
        "status": "CONTROLS_VALID_RESEARCH_STILL_BLOCKED" if not issues else "FAIL_CLOSED_INTEGRITY",
        "technical_integrity_pass": not issues,
        "integrity_failures": sorted(set(issues)),
        "source_sha256": sources,
        "source_order": ["SOFASCORE", "FLASHSCORE", "AUTHORIZED_FREE_APIS"],
        "automated_workflows_present": scheduled,
        "market_scope": {"total": total, "football": football,
                         "tennis": tennis, "counts": counts},
        "all_four_lanes": {
            "FOOTBALL_OVER25": {"research_frozen_pairs": pair_count},
            **{lane: {"original_prospective_counter": tennis_counts.get(lane)}
               for lane in REQUIRED_LANES[1:]}
        },
        "independent_poisson_oos": oos,
        "hybrid_bayesian_research": bayesian,
        "hybrid_three_model_oos": triple,
        "hybrid_team_venue_v2": team_v2,
        "hybrid_original_dual_freeze_lineage": original_dual_freeze,
        "hybrid_four_model_oos": four,
        "official_hybrid_p_matrix_comparison_certified": False,
        "all_42_markets_calibrated": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "production_p_matrix_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "challenge_completed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=Path(
        "evidence/governance/MATRIX_HYBRID_PERMANENT_CHALLENGE_GUARD_LAST.json"))
    args = parser.parse_args()
    if {"telegram", "notifications", "daily_prematch_reports"} & set(args.out.parts):
        raise SystemExit("CHALLENGE_GUARD_CANNOT_WRITE_SIGNALS")
    report = inspect(args.root)
    path = args.out if args.out.is_absolute() else args.root / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            previous = read_json(path)
            def durable(x):
                return {k: v for k, v in x.items() if k != "checked_at_utc"}
            if durable(previous) == durable(report):
                print(json.dumps({"unchanged": True, "status": report["status"],
                                  "physical_pairs": report["all_four_lanes"]["FOOTBALL_OVER25"]["research_frozen_pairs"]}))
                if not report["technical_integrity_pass"]:
                    raise SystemExit(2)
                return
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    path.write_text(json.dumps(report, ensure_ascii=False,
                               indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "integrity_failures": report["integrity_failures"],
                      "physical_pairs": report["all_four_lanes"]["FOOTBALL_OVER25"]["research_frozen_pairs"]},
                     sort_keys=True))
    if not report["technical_integrity_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
