"""Read-only 13-lane gate-600 decision ledger; never promotes models or Telegram.

Different populations must not be silently merged:
- 42-lane prospective PREMATCH freezes (not settled outcomes)
- historical 4,000 final-only calibration checkpoint
- period-goals research walk-forward
- separately dated post-gate settlement audit (can be stale)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
SUPERVISOR = ROOT / "evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"
CALIBRATION = ROOT / "evidence/governance/MATRIX_42_MARKET_ELITE_CALIBRATION_CLOSURE_28OCT2026.json"
PERIOD_LAB = ROOT / "evidence/api_football/period_goals_lab/MATRIX_PERIOD_GOALS_LAB_LAST.json"
SETTLEMENT_AUDIT = ROOT / "evidence/market_portfolio/MATRIX_GATE600_POST_AUDIT_LAST.json"
FIXED_5000 = ROOT / "evidence/api_football/calibration_v2/MATRIX_FOOTBALL_FIXED_PREFIX_5000_AUDIT_LAST.json"
OUTPUT = ROOT / "evidence/governance/MATRIX_13_MARKET_GATE600_COMMITTEE_LAST.json"

PERIOD_KEYS = {
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER": ("first_half_over_0_5", "first_half_over_1_5"),
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER": ("second_half_over_0_5", "second_half_over_1_5"),
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME": ("first_half_home_team_over_0_5",),
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY": ("first_half_away_team_over_0_5",),
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME": ("second_half_home_team_over_0_5",),
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY": ("second_half_away_team_over_0_5",),
}
HISTORICAL_KEYS = {
    "MATCH_RESULT_1X2": ("MATCH_RESULT_1X2",),
    "DOUBLE_CHANCE_1X": ("DOUBLE_CHANCE_1X",),
    "DOUBLE_CHANCE_X2": ("DOUBLE_CHANCE_X2",),
    "TOTAL_GOALS_OVER_UNDER": ("OVER_2_5", "UNDER_2_5"),
}
HISTORICAL_SELECTION = "TOTAL_GOALS_OVER_UNDER"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_JSON_OBJECT:{path}")
    return value


def _date(value: object) -> datetime:
    when = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if when.utcoffset() is None:
        raise ValueError("NAIVE_OR_MISSING_TIMESTAMP")
    return when.astimezone(timezone.utc)


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build(
    registry: dict[str, Any],
    supervisor: dict[str, Any],
    calibration: dict[str, Any],
    period_lab: dict[str, Any],
    settlement_audit: dict[str, Any],
    fixed_5000: dict[str, Any],
) -> dict[str, Any]:
    if registry.get("status") != "PASS" or registry.get("total_lanes") != 42:
        raise ValueError("REGISTRY_NOT_CERTIFIED_42")
    if supervisor.get("status") != "PASS" or supervisor.get("total_required_lanes") != 42:
        raise ValueError("SUPERVISOR_NOT_CERTIFIED_42")
    if set(registry.get("lanes", {})) != {
        str(row["market_key"]) for row in supervisor.get("rows", [])
    } or len(supervisor.get("rows", [])) != 42:
        raise ValueError("SUPERVISOR_REGISTRY_LANE_MISMATCH")
    if (registry.get("protections") or {}).get("real_money") != "BLOCKED":
        raise ValueError("REGISTRY_REAL_MONEY_NOT_BLOCKED")
    if (supervisor.get("invariants") or {}).get("real_money") != "BLOCKED":
        raise ValueError("SUPERVISOR_REAL_MONEY_NOT_BLOCKED")
    counts = [v.get("prospective_unique_count") for v in registry["lanes"].values()]
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError("INVALID_PROSPECTIVE_COUNT")
    if sum(counts) != registry.get("counts", {}).get("ledger_rows_total"):
        raise ValueError("REGISTRY_LEDGER_TOTAL_MISMATCH")
    if sum(n >= 600 for n in counts) != registry["counts"].get("lanes_at_600"):
        raise ValueError("REGISTRY_GATE600_COUNT_MISMATCH")
    if period_lab.get("mode") != "RESEARCH_WALK_FORWARD_SHADOW":
        raise ValueError("PERIOD_MODEL_NOT_RESEARCH_ONLY")
    if period_lab.get("production_authorized") is not False:
        raise ValueError("PERIOD_MODEL_UNEXPECTED_PRODUCTION")
    if (calibration.get("governance") or {}).get("promotion_is_not_implied_by_calibration") is not True:
        raise ValueError("CALIBRATION_GUARD_MISSING")
    if fixed_5000.get("automatic_promotion") is not False:
        raise ValueError("FIXED_PREFIX_AUTOPROMOTION_GUARD_MISSING")

    registry_ts = _date(registry["generated_at_utc"])
    audit_ts = _date(settlement_audit["generated_at_utc"])
    audit_is_fresh = audit_ts >= registry_ts
    audit_rows = {r["market_lane"]: r for r in settlement_audit.get("lanes", [])}
    if len(audit_rows) != len(settlement_audit.get("lanes", [])):
        raise ValueError("DUPLICATE_SETTLEMENT_AUDIT_LANE")
    sources = {
        "prospective_registry": registry["generated_at_utc"],
        "supervisor": supervisor["generated_at_utc"],
        "historical_calibration_head": calibration.get("source_head"),
        "period_lab": period_lab["generated_at_utc"],
        "gate600_settlement_audit": settlement_audit["generated_at_utc"],
        "fixed5000": fixed_5000["generated_at_utc"],
    }
    sup = {x["market_key"]: x for x in supervisor["rows"]}
    lanes = []
    for key, row in registry["lanes"].items():
        count = row["prospective_unique_count"]
        if count < 600:
            continue
        if row.get("sport") != "football":
            raise ValueError("UNEXPECTED_TENNIS_GATE600_REQUIRES_DEDICATED_ADJUDICATION")
        s = sup[key]
        prior = audit_rows.get(key)
        exact_settled = None
        settled_evidence = "NO_CURRENT_COHORT_SETTLEMENT_AUDIT"
        if prior:
            if audit_is_fresh:
                exact_settled = prior.get("exact_settled_count")
                settled_evidence = "CURRENT_AUDIT_SNAPSHOT_NOT_AUTOMATIC_PROMOTION"
            else:
                settled_evidence = "OLDER_AUDIT_REFERENCE_ONLY"
        historical = {}
        for historical_key in HISTORICAL_KEYS.get(key, ()):
            raw = calibration.get("checkpoint_4000", {}).get(historical_key)
            if raw:
                historical[historical_key] = {
                    "cohort": "HISTORICAL_FINAL_ONLY_4000_NOT_42_LANE_GATE600",
                    "eligible_rows": raw.get("eligible_rows"),
                    "brier_score": raw.get("brier_score"),
                    "log_loss": raw.get("log_loss"),
                    "status": raw.get("status"),
                }
        research = {}
        for period_key in PERIOD_KEYS.get(key, ()):
            m = period_lab.get("metrics", {}).get(period_key)
            if m:
                research[period_key] = {
                    "cohort": "PERIOD_GOALS_RESEARCH_WALK_FORWARD_NOT_42_LANE_GATE600",
                    "brier_score": m.get("brier"),
                    "observations": m.get("walk_forward_observations", period_lab.get("eligible_walk_forward_rows")),
                }
        if key == HISTORICAL_SELECTION and s.get("operational_state") == "ACTIVE":
            decision = "HISTORICAL_OVER25_ONLY_RUNTIME_GATES_STILL_REQUIRED"
            action = "CHECK_FRESH_CANONICAL_P_MATRIX_EXACT_BOOK_PRICE_SHARP_EV_AND_PRE_KICKOFF_BEFORE_ANY_SIGNAL"
        elif key == "DOUBLE_CHANCE_12":
            decision = "NO_GO_EXISTING_DIAGNOSTIC_CHALLENGER"
            action = "RETAIN_DIAGNOSTIC_NO_PROMOTION_UNTIL_NEW_PREDECLARED_VALIDATION"
        elif key in {"TEAM_TOTAL_GOALS_HOME", "TEAM_TOTAL_GOALS_AWAY"}:
            decision = "HOLD_NO_DEDICATED_OUTCOME_METRIC"
            action = "BUILD_SEPARATE_PIT_FINAL_ONLY_CALIBRATION_WITH_EXACT_COHORT_JOIN"
        elif key in PERIOD_KEYS:
            decision = "HOLD_PERIOD_GOALS_RESEARCH_ONLY_PRICE_PROMOTION_REQUIRED"
            action = "COMPLETE_DEDICATED_PREMATCH_VALIDATION_PRICE_MAPPING_AND_FORMAL_PROMOTION"
        else:
            decision = "HOLD_FORMAL_PROMOTION_AND_EXACT_COHORT_SETTLEMENT_PENDING"
            action = "REBUILD_FRESH_GATE600_EXACT_FINAL_SETTLEMENT_AUDIT_WITH_FORMAL_PROMOTION_REVIEW"
        lanes.append({
            "market_key": key,
            "display_name": row.get("display_name"),
            "prospective_valid_freezes": count,
            "prospective_freeze_gate_600_reached": True,
            "current_exact_settled_count_verified": exact_settled,
            "settlement_evidence": settled_evidence,
            "older_audit_exact_settled_reference": prior.get("exact_settled_count") if prior and not audit_is_fresh else None,
            "older_audit_at_utc": settlement_audit.get("generated_at_utc") if prior and not audit_is_fresh else None,
            "historical_4000_metrics_separate_cohort": historical,
            "period_goals_research_metrics_separate_cohort": research,
            "supervisor_state": s.get("operational_state"),
            "decision": decision,
            "required_next_action": action,
            "automatically_promoted": False,
            "telegram_signal_authorized_by_this_audit": False,
        })
    lanes.sort(key=lambda x: (-x["prospective_valid_freezes"], x["market_key"]))
    if len(lanes) != 13 or len({r["market_key"] for r in lanes}) != 13:
        raise ValueError("EXACT_13_GATE600_LANES_NOT_PRESENT")
    return {
        "schema": "MATRIX_13_MARKET_GATE600_COMMITTEE_V1",
        "status": "PASS_READ_ONLY_DIAGNOSTIC_NOT_PROMOTION_CERTIFICATION",
        "source_timestamps_utc": sources,
        "source_hashes_sha256": {
            "registry": _hash(registry),
            "supervisor": _hash(supervisor),
            "calibration": _hash(calibration),
            "period_lab": _hash(period_lab),
            "settlement_audit": _hash(settlement_audit),
            "fixed_5000": _hash(fixed_5000),
        },
        "summary": {
            "portfolio_lanes": 42,
            "football_lanes": 30,
            "tennis_lanes": 12,
            "gate600_reached": len(lanes),
            "current_exact_settled_600_certified_by_this_audit": 0,
            "period_research_observations_not_gate600_settlements": period_lab.get("eligible_walk_forward_rows"),
            "fixed_prefix_5000_last_recorded_settled": fixed_5000.get("current_settled_count"),
            "fixed_prefix_5000_audit_opened": fixed_5000.get("metrics_opened") is True,
            "gate600_settlement_audit_is_at_least_as_recent_as_registry": audit_is_fresh,
        },
        "lanes": lanes,
        "committee_roles": [
            "QUANT_VALIDATION", "PIT_TEMPORAL_INTEGRITY", "SETTLEMENT_COHORT_AUDIT",
            "PERIOD_GOALS_MODELLING", "ODDS_SHARP_CLV", "TELEGRAM_RELIABILITY",
            "TEST_ENGINEERING", "EVIDENCE_GOVERNANCE",
        ],
        "governance": {
            "no_automatic_promotion": True,
            "no_odds_to_probability": True,
            "historical_4000_not_42_lane_settlement": True,
            "period_walk_forward_not_42_lane_settlement": True,
            "stale_post600_snapshot_never_current_proof": True,
            "post_start_backfill_forbidden": True,
            "missing_not_zero": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "telegram_messages_sent": 0,
        },
    }


def main() -> None:
    result = build(*(_read(p) for p in (
        REGISTRY, SUPERVISOR, CALIBRATION, PERIOD_LAB, SETTLEMENT_AUDIT, FIXED_5000,
    )))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "real_money": "BLOCKED"}, sort_keys=True))


if __name__ == "__main__":
    main()
