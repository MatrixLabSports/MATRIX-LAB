from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_market_shadow_p_matrix import PARAMS_OVER25, build_shadow_p_matrix

POLICY = {
    "betano": ["betano"],
    "betplay": ["betplay"],
    "rushbet": ["rushbet", "rush bet"],
}
DIAGNOSTIC = {"pinnacle": ["pinnacle"]}


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def match_book(name: str, mapping: dict[str, list[str]]) -> str | None:
    n = norm(name)
    for key, tokens in mapping.items():
        if any(norm(token) in n for token in tokens):
            return key
    return None


def odd(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if x > 1.0 else None


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def resolve_over25_signal_governance(root: Path) -> dict[str, Any]:
    """Resolve market-scoped signal authority without silently promoting sport-wide/real-money scope."""
    promotion_path = root / "evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
    legacy_path = root / "evidence/api_football/market_governance/market_governance.json"
    reasons: list[str] = []
    try:
        promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    except Exception:
        promotion = {}
        reasons.append("PROMOTION_ARTIFACT_MISSING_OR_INVALID")
    try:
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    except Exception:
        legacy = {}
        reasons.append("LEGACY_MARKET_GOVERNANCE_MISSING_OR_INVALID")

    market_rows = legacy.get("markets") if isinstance(legacy, dict) else None
    over_row = None
    if isinstance(market_rows, list):
        over_row = next(
            (x for x in market_rows if isinstance(x, dict) and x.get("market") == "over_2_5"),
            None,
        )
    if not isinstance(over_row, dict):
        reasons.append("LEGACY_OVER25_ROW_MISSING")
        over_row = {}

    expected_params = {
        "a": float(PARAMS_OVER25["a"]),
        "b": float(PARAMS_OVER25["b"]),
        "c": float(PARAMS_OVER25["c"]),
    }
    frozen = promotion.get("frozen_parameters")
    actual_params = None
    if isinstance(frozen, dict) and all(k in frozen for k in ("a", "b", "c")):
        actual_params = {k: float(frozen[k]) for k in ("a", "b", "c")}
    else:
        reasons.append("PROMOTION_FROZEN_PARAMETERS_MISSING")

    checks = {
        "promotion_market_over25": promotion.get("market") == "OVER_2_5",
        "promotion_status_pass": promotion.get("promotion_status") == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
        "engine_executable_for_p_matrix": promotion.get("engine_executable_for_p_matrix") is True,
        "governed_p_matrix_engine_available": promotion.get("governed_p_matrix_engine_available") is True,
        "promotion_scope_signal_only": promotion.get("promotion_scope") == "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
        "promotion_real_money_blocked": (promotion.get("protections") or {}).get("real_money") == "BLOCKED",
        "promotion_automatic_wagering_false": (promotion.get("protections") or {}).get("automatic_wagering") is False,
        "legacy_over25_holdout_gate_passed": over_row.get("market_holdout_gate_passed") is True,
        "legacy_challenger_identity_matches": over_row.get("challenger_name") == "calibrated_log_pool_v1",
        "frozen_parameters_match_runtime": actual_params == expected_params,
    }
    for key, passed in checks.items():
        if not passed:
            reasons.append(f"FAILED:{key}")

    authorized = not reasons
    return {
        "schema": "MATRIX_FOOTBALL_OVER25_SIGNAL_GOVERNANCE_RESOLUTION_V1",
        "market": "OVER_2_5",
        "signal_generation_authorized": authorized,
        "authoritative_market_scoped_status": (
            promotion.get("promotion_status") if authorized else "BLOCKED_GOVERNANCE"
        ),
        "promotion_artifact": promotion_path.as_posix(),
        "legacy_market_governance_artifact": legacy_path.as_posix(),
        "legacy_sport_wide_engine_promoted": legacy.get("governed_engine_promoted"),
        "legacy_sport_wide_gate_scope": "SPORT_WIDE_OR_REAL_MONEY",
        "market_scoped_scope": "SIGNAL_GENERATION_ONLY",
        "precedence_rule": (
            "MARKET_SCOPED_PROMOTION_GOVERNS_OVER25_SIGNAL_GENERATION; "
            "LEGACY_SPORT_WIDE_GATE_CONTINUES_TO_GOVERN_SPORT_WIDE_OR_REAL_MONEY"
        ),
        "runtime_parameters": expected_params,
        "promotion_parameters": actual_params,
        "checks": checks,
        "blockers": reasons,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def latest_cycle(root: Path, target_date: str) -> Path:
    base = root / "evidence" / "api_football" / "prospective_daily" / target_date
    candidates = sorted(p for p in base.glob("*") if p.is_dir() and (p / "cycle_summary.json").exists())
    if not candidates:
        raise SystemExit(f"NO_PROSPECTIVE_CYCLE:{target_date}")
    valid = []
    for p in candidates:
        try:
            j = json.loads((p / "cycle_summary.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") == "PASS" and j.get("target_date_bogota") == target_date:
            valid.append(p)
    if not valid:
        raise SystemExit(f"NO_VALID_PROSPECTIVE_CYCLE:{target_date}")
    return valid[-1]


def _cycle_ready_count(cycle: Path) -> int:
    try:
        j = json.loads((cycle / "cycle_summary.json").read_text(encoding="utf-8"))
        return int(((j.get("canonical") or {}).get("ready_input_count")) or 0)
    except Exception:
        return 0


def select_probability_cycle(root: Path, target_date: str, inventory_cycle: Path) -> Path:
    base = root / "evidence" / "api_football" / "prospective_daily" / target_date
    candidates = []
    for p in sorted(x for x in base.glob("*") if x.is_dir() and x <= inventory_cycle):
        summary = p / "cycle_summary.json"
        canonical = p / "canonical_analysis" / "manifest.json"
        raw_dir = p / "history" / "raw"
        if not summary.exists() or not canonical.exists() or not raw_dir.exists():
            continue
        try:
            j = json.loads(summary.read_text(encoding="utf-8"))
            m = json.loads(canonical.read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") != "PASS" or j.get("target_date_bogota") != target_date:
            continue
        if m.get("status") != "PASS" or m.get("real_money") != "BLOCKED":
            continue
        ready = int(((j.get("canonical") or {}).get("ready_input_count")) or 0)
        candidates.append((ready, p))
    if not candidates:
        return inventory_cycle
    # Prefer the same-day cycle with the widest physically frozen PIT coverage.
    # Ties prefer the newest cycle. This avoids losing valid frozen probabilities
    # merely because a later refresh hits the provider's daily reserve.
    candidates.sort(key=lambda item: (item[0], item[1].name))
    return candidates[-1][1]


def _current_future_fixture_ids(inventory_cycle: Path) -> set[str]:
    path = inventory_cycle / "fixtures" / "future_fixture_registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        str(row.get("provider_fixture_id") or "")
        for row in (registry.get("events") or [])
        if isinstance(row, dict) and row.get("provider_fixture_id")
    }


def dedupe(xs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, float]] = set()
    out: list[dict[str, Any]] = []
    for x in xs:
        key = (str(x["house_key"]), float(x["decimal_odds"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def build(target_date: str, api_key: str, root: Path = Path(".")) -> dict[str, Any]:
    api_key = str(api_key or "").strip()
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    api_key.encode("ascii")

    governance = resolve_over25_signal_governance(root)
    inventory_cycle = latest_cycle(root, target_date)
    cycle = select_probability_cycle(root, target_date, inventory_cycle)
    canonical, manifest = load_chunked_canonical_bundle(cycle / "canonical_analysis")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    p_matrix = build_shadow_p_matrix(
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        raw_dir=cycle / "history" / "raw",
        generated_at=generated_at,
    )
    current_future_ids = _current_future_fixture_ids(inventory_cycle)
    if current_future_ids:
        p_matrix["rows"] = [
            row for row in p_matrix.get("rows", [])
            if str(row.get("fixture_id") or "") in current_future_ids
        ]
        p_matrix["blocked"] = [
            row for row in p_matrix.get("blocked", [])
            if str(row.get("fixture_id") or "") in current_future_ids
        ]
        p_matrix["scored_count"] = len(p_matrix["rows"])
        p_matrix["blocked_count"] = len(p_matrix["blocked"])
    p_matrix["inventory_cycle"] = inventory_cycle.relative_to(root).as_posix()
    p_matrix["probability_source_cycle"] = cycle.relative_to(root).as_posix()
    p_matrix["same_day_probability_carry_forward"] = cycle != inventory_cycle

    report_root = root / "evidence" / "api_football" / "daily_prematch_reports" / target_date
    report_root.mkdir(parents=True, exist_ok=True)
    p_path = report_root / "p_matrix_shadow_current.json"
    p_path.write_text(
        json.dumps(p_matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ev_root = report_root / "over25_shadow_ev"
    raw_root = ev_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = requests.Session()
    rows: list[dict[str, Any]] = []
    calls = 0

    for row in p_matrix.get("rows", []):
        fixture_id = str(row["fixture_id"])
        kickoff = parse_utc(row["kickoff_utc"])
        probability = float(row["p_matrix_shadow"]["over_2_5"])
        match = f'{row.get("home_team")} vs {row.get("away_team")}'

        if kickoff <= now:
            rows.append({
                "fixture_id": fixture_id,
                "match": match,
                "kickoff_utc": row["kickoff_utc"],
                "p_over_2_5": probability,
                "decision": "BLOCKED",
                "reason": "EVENT_NOT_FUTURE_AT_ODDS_QUERY",
                "policy_offers": [],
                "diagnostic_offers": [],
                "best_policy_offer": None,
            })
            continue

        response = client.get(
            "https://v3.football.api-sports.io/odds",
            headers={"x-apisports-key": api_key},
            params={"fixture": fixture_id},
            timeout=(10, 30),
        )
        calls += 1
        body = bytes(response.content)
        (raw_root / f"fixture_{fixture_id}.bin").write_bytes(body)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        errors = payload.get("errors") if isinstance(payload, dict) else None
        policy_offers: list[dict[str, Any]] = []
        diagnostic_offers: list[dict[str, Any]] = []

        if 200 <= response.status_code < 300 and errors in ({}, [], None):
            for fixture_row in payload.get("response", []) or []:
                if not isinstance(fixture_row, dict):
                    continue
                for bookmaker in fixture_row.get("bookmakers", []) or []:
                    if not isinstance(bookmaker, dict):
                        continue
                    bookmaker_name = str(bookmaker.get("name") or "")
                    policy_key = match_book(bookmaker_name, POLICY)
                    diagnostic_key = match_book(bookmaker_name, DIAGNOSTIC)
                    if not policy_key and not diagnostic_key:
                        continue
                    for bet in bookmaker.get("bets", []) or []:
                        if not isinstance(bet, dict):
                            continue
                        try:
                            bet_id = int(bet.get("id"))
                        except Exception:
                            continue
                        bet_name = str(bet.get("name") or "").strip()
                        if bet_id != 5 or bet_name.casefold() != "goals over/under":
                            continue
                        for value in bet.get("values", []) or []:
                            if not isinstance(value, dict):
                                continue
                            if str(value.get("value") or "").strip().casefold() != "over 2.5":
                                continue
                            decimal = odd(value.get("odd"))
                            if decimal is None:
                                continue
                            offer = {
                                "house_key": policy_key or diagnostic_key,
                                "bookmaker_id": bookmaker.get("id"),
                                "bookmaker_name": bookmaker_name,
                                "bet_id": bet_id,
                                "bet_name": bet_name,
                                "label": "Over 2.5",
                                "decimal_odds": decimal,
                                "break_even_probability": 1.0 / decimal,
                                "p_matrix": probability,
                                "ev": probability * decimal - 1.0,
                                "odds_used_to_generate_probability": False,
                            }
                            (policy_offers if policy_key else diagnostic_offers).append(offer)

        policy_offers = dedupe(policy_offers)
        diagnostic_offers = dedupe(diagnostic_offers)
        eligible = [x for x in policy_offers if float(x["decimal_odds"]) > 1.50]
        best = max(eligible, key=lambda x: float(x["ev"])) if eligible else None

        if governance["signal_generation_authorized"] is not True:
            decision = "BLOCKED"
            reason = "OVER25_SIGNAL_GOVERNANCE_NOT_AUTHORIZED"
        elif best is None:
            decision = "BLOCKED"
            reason = "NO_EXACT_POLICY_HOUSE_OVER25_ODDS_ABOVE_1_50"
        elif float(best["ev"]) > 0:
            decision = "BET_SHADOW"
            reason = "EXACT_POLICY_HOUSE_ODDS_AND_POSITIVE_EV"
        else:
            decision = "NO_BET"
            reason = "EXACT_POLICY_HOUSE_ODDS_BUT_EV_NOT_POSITIVE"

        rows.append({
            "fixture_id": fixture_id,
            "match": match,
            "league_id": row.get("league_id"),
            "kickoff_utc": row["kickoff_utc"],
            "p_over_2_5": probability,
            "fair_decimal_odds": 1.0 / probability,
            "policy_offers": policy_offers,
            "diagnostic_offers": diagnostic_offers,
            "best_policy_offer": best,
            "decision": decision,
            "reason": reason,
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "provider_http_status": int(response.status_code),
            "provider_errors": errors,
        })

    for blocked in p_matrix.get("blocked", []):
        rows.append({
            "fixture_id": str(blocked.get("fixture_id") or ""),
            "match": None,
            "kickoff_utc": None,
            "p_over_2_5": None,
            "policy_offers": [],
            "diagnostic_offers": [],
            "best_policy_offer": None,
            "decision": "BLOCKED",
            "reason": "P_MATRIX_BLOCKED:" + str(blocked.get("reason")),
        })

    order = {"BET_SHADOW": 0, "NO_BET": 1, "BLOCKED": 2}
    rows.sort(
        key=lambda x: (
            order.get(str(x["decision"]), 9),
            -float((x.get("best_policy_offer") or {}).get("ev", -999)),
            str(x.get("kickoff_utc") or ""),
            str(x.get("fixture_id") or ""),
        )
    )
    bets = [x for x in rows if x["decision"] == "BET_SHADOW"]
    no_bets = [x for x in rows if x["decision"] == "NO_BET"]
    blocked_rows = [x for x in rows if x["decision"] == "BLOCKED"]

    output = {
        "schema": "MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV_V2",
        "generated_at_utc": now.isoformat(),
        "target_date_bogota": target_date,
        "source_cycle": cycle.as_posix(),
        "inventory_cycle": inventory_cycle.as_posix(),
        "same_day_probability_carry_forward": cycle != inventory_cycle,
        "market": "OVER_2_5",
        "probability_engine": "calibrated_log_pool_v1",
        "probability_status": (
            "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY"
            if governance["signal_generation_authorized"]
            else "BLOCKED_GOVERNANCE"
        ),
        "market_governance_status": governance["authoritative_market_scoped_status"],
        "signal_generation_authorized": governance["signal_generation_authorized"],
        "governance_resolution": governance,
        "exact_market_binding": {"bet_id": 5, "bet_name": "Goals Over/Under", "value": "Over 2.5"},
        "policy_houses": ["Betano", "BetPlay", "RushBet"],
        "diagnostic_only": ["Pinnacle"],
        "minimum_decimal_odds_exclusive": 1.50,
        "ev_formula": "P_MATRIX * DECIMAL_ODDS - 1",
        "bet_shadow_requires_positive_ev": True,
        "network_calls": calls,
        "p_matrix_scored_count": int(p_matrix["scored_count"]),
        "p_matrix_blocked_count": int(p_matrix["blocked_count"]),
        "decision_counts": {
            "BET_SHADOW": len(bets),
            "NO_BET": len(no_bets),
            "BLOCKED": len(blocked_rows),
        },
        "bet_shadow": bets,
        "no_bet": no_bets,
        "blocked": blocked_rows,
        "all_rows": rows,
        "protections": {
            "probability_frozen_before_odds_query": True,
            "odds_used_to_generate_probability": False,
            "target_outcomes_used": False,
            "broad_market_matching_forbidden": True,
            "pinnacle_not_executable_house": True,
            "bwin_excluded": True,
            "physical_house_crosscheck_required": True,
            "house_selection_policy": "COMPARE_BETANO_BETPLAY_RUSHBET_AND_SELECT_BEST_VALID_EXACT_MARKET_OFFER",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    blob = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    output["sha256_without_self"] = hashlib.sha256(blob).hexdigest()

    out_path = ev_root / "MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "target_date_bogota": target_date,
        "cycle_root": cycle.as_posix(),
        "inventory_cycle_root": inventory_cycle.as_posix(),
        "same_day_probability_carry_forward": cycle != inventory_cycle,
        "ready_inputs": int(p_matrix["source_ready_input_count"]),
        "p_matrix_scored": int(p_matrix["scored_count"]),
        "p_matrix_blocked": int(p_matrix["blocked_count"]),
        "network_calls": calls,
        "decision_counts": output["decision_counts"],
        "top_shadow": [
            {
                "fixture_id": x["fixture_id"],
                "match": x["match"],
                "p": x["p_over_2_5"],
                "house": x["best_policy_offer"]["bookmaker_name"],
                "odds": x["best_policy_offer"]["decimal_odds"],
                "ev": x["best_policy_offer"]["ev"],
            }
            for x in bets[:15]
        ],
        "real_money": "BLOCKED",
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", required=True)
    args = parser.parse_args()
    result = build(args.target_date, os.environ.get("API_FOOTBALL_KEY", ""))
    assert result["protections"]["probability_frozen_before_odds_query"] is True
    assert result["protections"]["odds_used_to_generate_probability"] is False
    assert result["protections"]["automatic_wagering"] is False
    assert result["protections"]["real_money"] == "BLOCKED"
    for row in result["bet_shadow"]:
        best = row["best_policy_offer"]
        assert best["decimal_odds"] > 1.50
        assert best["ev"] > 0
        assert best["bet_id"] == 5
        assert best["bet_name"] == "Goals Over/Under"
        assert best["label"] == "Over 2.5"
        assert best["house_key"] in {"betano", "betplay", "rushbet"}


if __name__ == "__main__":
    main()
