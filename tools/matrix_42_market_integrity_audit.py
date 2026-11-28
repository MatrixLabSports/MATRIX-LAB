"""Read-only integrity audit of MATRIX's 42 supervised market lanes.

Sources are existing repository evidence. Counts mean unique prospective
market-lane freeze observations, NOT settled outcomes, calibrated models,
unique sporting events, or authorized betting opportunities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REG = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
SUP = Path("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
BOARD = Path("evidence/market_portfolio/MATRIX_42_LANE_ACTION_BOARD_LAST.json")
ZERO = Path("evidence/market_portfolio/MATRIX_42_LANE_ZERO_PROSPECTIVE_BLOCKERS_LAST.json")
GATE = Path("evidence/market_portfolio/MATRIX_GATE600_POST_AUDIT_LAST.json")
RESULT_SCHEMA = "MATRIX_42_MARKET_INTEGRITY_RECONCILIATION_V1"


def when(value: str) -> datetime:
    obj = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if obj.utcoffset() is None:
        raise ValueError("MARKET_EVIDENCE_NAIVE_TIMESTAMP")
    return obj.astimezone(timezone.utc)


def audit(reg: dict, sup: dict, board: dict, zero: dict, gate: dict) -> dict:
    lanes = reg.get("lanes")
    if not isinstance(lanes, dict) or len(lanes) != 42:
        raise ValueError("MARKET_REGISTRY_NOT_EXACTLY_42")
    supervisor = sup.get("rows")
    if not isinstance(supervisor, list) or len(supervisor) != 42:
        raise ValueError("MARKET_SUPERVISOR_NOT_EXACTLY_42")
    by_id = {r["market_key"]: r for r in supervisor}
    if len(by_id) != 42 or set(by_id) != set(lanes):
        raise ValueError("MARKET_REGISTRY_SUPERVISOR_KEY_CONFLICT")
    blockers = zero.get("rows")
    if not isinstance(blockers, list):
        raise ValueError("MARKET_ZERO_BLOCKER_ROWS_MISSING")
    blocker_by_id = {r["market_lane"]: r for r in blockers}
    if len(blocker_by_id) != len(blockers):
        raise ValueError("MARKET_DUPLICATE_ZERO_BLOCKER")
    counts = Counter()
    observations = 0
    reported = []
    for key in sorted(lanes):
        a, b = lanes[key], by_id[key]
        if a["sport"] != b["sport"] or a["display_name"] != b["display_name"]:
            raise ValueError("MARKET_NAME_OR_SPORT_MISMATCH")
        n = a["prospective_unique_count"]
        if type(n) is not int or n < 0:
            raise ValueError("MARKET_INVALID_COUNT")
        g = a["gates"]["600"]["count"]
        # Gate counters are capped at their threshold; raw observations
        # continue growing after a gate is opened.
        if type(g) is not int or g != min(n, 600):
            raise ValueError("MARKET_COUNT_GATE_DIVERGENCE")
        observations += n
        counts[a["sport"]] += 1
        counts["with_prospective" if n else "zero_prospective"] += 1
        if n >= 600:
            counts["at_600"] += 1
        if n == 0 and key not in blocker_by_id:
            raise ValueError("MARKET_MISSING_ZERO_BLOCKER")
        if n and key in blocker_by_id:
            raise ValueError("MARKET_STALE_ZERO_BLOCKER")
        if (a.get("production_authorized_by_registry") is True
            or b.get("production_authorized") is True):
            counts["production_state_claims"] += 1
        reported.append({
            "lane": key,
            "display_name": a["display_name"],
            "sport": a["sport"],
            "unique_prospective_market_observations": n,
            "gate_600_reached": n >= 600,
            "independently_settled_600_verified_by_this_audit": False,
            "calibration_pass_verified_by_this_audit": False,
            "registry_production_authorized": a.get("production_authorized_by_registry") is True,
            "supervisor_state": b["operational_state"],
            "supervisor_production_claim": b.get("production_authorized") is True,
            "production_signal_authorized_by_this_audit": False,
            "blocker": blocker_by_id[key]["blocker"] if n == 0 else None,
        })
    if counts["football"] != 30 or counts["tennis"] != 12:
        raise ValueError("MARKET_30_FOOTBALL_12_TENNIS_REQUIRED")
    if (observations != reg["counts"]["ledger_rows_total"]
        or counts["at_600"] != reg["counts"]["lanes_at_600"]
        or counts["with_prospective"] != reg["counts"]["lanes_with_any_valid_prospective"]
        or counts["zero_prospective"] != zero["zero_prospective_lane_count"]):
        raise ValueError("MARKET_COUNTER_TOTALS_NOT_RECONCILED")
    board_time = when(board["generated_at_utc"])
    reg_time = when(reg["generated_at_utc"])
    if board_time > reg_time:
        raise ValueError("MARKET_BOARD_NEWER_THAN_REGISTRY")
    gate_rows = gate.get("lanes", [])
    gate_status = gate.get("audit_overall_verdict")
    gate_count = len(gate_rows)
    older_board_at600 = board.get("counts", {}).get("lanes_at_600")
    source = reg.get("source_inventory", {})
    football = source.get("football", {})
    tennis = source.get("tennis", {})
    return {
        "schema": RESULT_SCHEMA,
        "status": "READ_ONLY_42_MARKETS_RECONCILED_NOT_PRODUCTION_CERTIFICATION",
        "as_of_registry_utc": reg["generated_at_utc"],
        "old_action_board_utc": board["generated_at_utc"],
        "gate600_audit_utc": gate["generated_at_utc"],
        "market_counts": {
            "all": 42, "football": counts["football"], "tennis": counts["tennis"],
            "with_prospective": counts["with_prospective"],
            "zero_prospective": counts["zero_prospective"],
            "at_600_freezes": counts["at_600"],
            "market_lane_observation_rows": observations,
        },
        "dated_difference": {
            "old_board_market_lanes_at_600": older_board_at600,
            "latest_registry_market_lanes_at_600": counts["at_600"],
            "different_snapshot_dates": board_time != reg_time,
            "not_same_settled_cohort": True,
        },
        "latest_available_gate600_settlement_audit": {
            "as_of_utc": gate["generated_at_utc"],
            "market_count_in_older_audit": gate_count,
            "verdict": gate_status,
            "rows": [
                {"lane": x["market_lane"],
                 "prospective_at_older_board": x.get("action_board_count"),
                 "verified_settled_at_older_audit": x.get("exact_settled_count"),
                 "verdict": x.get("verdict")}
                for x in gate_rows
            ],
            "not_a_current_audit_of_all_13": True,
        },
        "producer_input_readiness_at_registry_time": {
            "football_inventory_source": football.get("source_path"),
            "football_inventory_fresh": football.get("source_usable_for_new_freeze_now") is True,
            "football_inventory_blocker": football.get("blocker"),
            "tennis_today_reconciled": tennis.get("today", {}).get("available") is True,
            "tennis_tomorrow_reconciled": tennis.get("tomorrow", {}).get("available") is True,
        },
        "production_claims_require_separate_adjudication": [
            x["lane"] for x in reported if x["supervisor_production_claim"]
        ],
        "no_auto_promotion": True,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "markets": reported,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = [REG, SUP, BOARD, ZERO, GATE]
    raws = [(args.root / p).read_bytes() for p in roots]
    result = audit(*(json.loads(raw) for raw in raws))
    result["source_file_sha256"] = {
        str(p): hashlib.sha256(raw).hexdigest()
        for p, raw in zip(roots, raws)
    }
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False,
                                      indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "counts": result["market_counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
