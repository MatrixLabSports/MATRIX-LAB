from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("evidence/api_football")
OUT = ROOT / "governance/MATRIX_1X2_PROMOTION_READINESS_LAST.json"

CHECKPOINT = ROOT / "calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json"
OOS_STATE = ROOT / "calibration_v2/OOS_4001_5000_STATE.json"
LANE_STATE = ROOT / "calibration_v2/lanes/1x2/state.json"
P_MATRIX_PROMOTION = ROOT / "governance/1x2_p_matrix_promotion.json"
QUOTE_CONTRACT = ROOT / "governance/1x2_execution_quote_contract.json"
TELEGRAM_ENGINE = Path("tools/telegram_1x2_signal_engine.py")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def build() -> dict[str, Any]:
    checkpoint = load(CHECKPOINT)
    oos = load(OOS_STATE)
    lane = load(LANE_STATE)

    cp = (checkpoint.get("markets") or {}).get("1x2") or {}

    checks = {
        "checkpoint_4000_complete": cp.get("eligible_rows") == 4000 and cp.get("missing_rows") == 0,
        "checkpoint_not_automatic_promotion": (checkpoint.get("adjudication") or {}).get("market_promotion") == "NOT_AUTOMATICALLY_AUTHORIZED",
        "lane_no_backfill": lane.get("no_backfill") is True,
        "lane_parameters_frozen": lane.get("parameter_tuning_allowed") is False,
        "odds_not_used_for_probability": (checkpoint.get("governance") or {}).get("odds_used_to_generate_probability") is False,
        "oos_target_reached": int(oos.get("current_oos_observations") or 0) >= int(oos.get("target_oos_observations") or 1000),
        "oos_metrics_opened": oos.get("metrics_opened") is True,
        "oos_outcomes_read": int(oos.get("outcomes_read_for_oos_metrics") or 0) >= int(oos.get("target_oos_observations") or 1000),
        "dedicated_quote_path_certified": QUOTE_CONTRACT.exists(),
        "telegram_signal_engine_certified": TELEGRAM_ENGINE.exists(),
        "explicit_signal_promotion_exists": P_MATRIX_PROMOTION.exists(),
    }

    blockers = []
    if not checks["oos_target_reached"]:
        blockers.append("OOS_4001_5000_NOT_COMPLETE")
    if not checks["oos_metrics_opened"] or not checks["oos_outcomes_read"]:
        blockers.append("OOS_1000_METRICS_NOT_OPENED")
    if not checks["explicit_signal_promotion_exists"]:
        blockers.append("NO_EXPLICIT_GOVERNED_1X2_P_MATRIX_PROMOTION")
    if not checks["dedicated_quote_path_certified"]:
        blockers.append("NO_DEDICATED_1X2_QUOTE_REVALIDATION_CONTRACT")
    if not checks["telegram_signal_engine_certified"]:
        blockers.append("NO_1X2_TELEGRAM_SIGNAL_ENGINE")

    promotion_allowed = all([
        checks["checkpoint_4000_complete"],
        checks["checkpoint_not_automatic_promotion"],
        checks["lane_no_backfill"],
        checks["lane_parameters_frozen"],
        checks["odds_not_used_for_probability"],
        checks["oos_target_reached"],
        checks["oos_metrics_opened"],
        checks["oos_outcomes_read"],
        checks["dedicated_quote_path_certified"],
        checks["telegram_signal_engine_certified"],
        checks["explicit_signal_promotion_exists"],
    ])

    return {
        "schema": "MATRIX_1X2_PROMOTION_READINESS_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "market": "1X2",
        "status": "PASS_PROMOTION_READY" if promotion_allowed else "BLOCKED_NOT_PROMOTABLE",
        "promotion_allowed": promotion_allowed,
        "signal_status": "SIGNAL_AUTHORIZED" if promotion_allowed else "RESEARCH_ONLY",
        "checks": checks,
        "blockers": blockers,
        "physical_state": {
            "checkpoint_calibration_rows": cp.get("eligible_rows"),
            "checkpoint_accuracy": (cp.get("metrics") or {}).get("accuracy"),
            "checkpoint_brier_score": (cp.get("metrics") or {}).get("brier_score"),
            "checkpoint_log_loss": (cp.get("metrics") or {}).get("log_loss"),
            "lane_settlement_count": lane.get("settlement_count"),
            "lane_pending_settlement_count": lane.get("pending_settlement_count"),
            "lane_freeze_observation_count": lane.get("freeze_observation_count"),
            "oos_current_observations": oos.get("current_oos_observations"),
            "oos_target_observations": oos.get("target_oos_observations"),
            "oos_remaining": oos.get("remaining_to_1000"),
            "oos_metrics_opened": oos.get("metrics_opened"),
        },
        "governance": {
            "next_required_action": "COMPLETE_PREREGISTERED_OOS_1000_WITHOUT_TUNING_THEN_EVALUATE",
            "minimum_decimal_odds_exclusive": 1.50,
            "positive_ev_required": True,
            "p_matrix_must_exist_before_odds": True,
            "odds_may_not_generate_probability": True,
            "no_backfill": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "promotion_before_all_gates": "FORBIDDEN",
        },
        "sources": {
            "checkpoint": str(CHECKPOINT),
            "oos_state": str(OOS_STATE),
            "lane_state": str(LANE_STATE),
            "p_matrix_promotion": str(P_MATRIX_PROMOTION),
            "quote_contract": str(QUOTE_CONTRACT),
            "telegram_engine": str(TELEGRAM_ENGINE),
        },
    }


def main() -> None:
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "market": out["market"],
        "status": out["status"],
        "promotion_allowed": out["promotion_allowed"],
        "blockers": out["blockers"],
        "oos_current": out["physical_state"]["oos_current_observations"],
        "oos_remaining": out["physical_state"]["oos_remaining"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
