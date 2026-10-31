#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(rel):
    with (ROOT / rel).open("r", encoding="utf-8") as f:
        return json.load(f)

def build_report():
    checkpoint = load("evidence/api_football/calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
    period = load("evidence/api_football/period_goals_lab/MATRIX_PERIOD_GOALS_LAB_LAST.json")
    registry = load("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
    dc12 = load("evidence/api_football/calibration_v2/baseline/double_chance_12.json")
    promotion = load("evidence/api_football/governance/over_2_5_p_matrix_promotion.json")
    oos = load("evidence/api_football/calibration_v2/OOS_4001_5000_STATE.json")

    core = {}
    for key in ("1x2", "double_chance_1x", "double_chance_x2", "over_2_5", "under_2_5"):
        row = checkpoint["markets"][key]
        m = row["metrics"]
        core[key] = {
            "eligible_rows": row["eligible_rows"],
            "derived_from": row.get("derived_from"),
            "brier_score": m["brier_score"],
            "log_loss": m["log_loss"],
            "ece": m.get("ece", m.get("calibration", {}).get("macro_ece")),
            "accuracy": m.get("accuracy"),
            "promotion_authorized": key == "over_2_5" and promotion["promotion_status"] == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
        }

    return {
        "schema": "MATRIX_42_MARKET_ELITE_CALIBRATION_CLOSURE_V1",
        "source_head": "409cd106711a0b4e54c843f74e278bb81acf996a",
        "governance": {
            "parameter_refit": False,
            "parameter_search": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "odds_used_to_generate_probability": False,
            "promotion_is_not_implied_by_calibration": True,
        },
        "portfolio": {
            "total_lanes": registry["total_lanes"],
            "football_lanes": registry["football_lanes"],
            "tennis_lanes": registry["tennis_lanes"],
            "lanes_at_600": registry["counts"]["lanes_at_600"],
            "lanes_with_any_valid_prospective": registry["counts"]["lanes_with_any_valid_prospective"],
        },
        "checkpoint_4000": core,
        "period_goals_walk_forward": {
            "model": period["model"],
            "mode": period["mode"],
            "observations": period["eligible_walk_forward_rows"],
            "metrics": period["metrics"],
            "production_authorized": period["production_authorized"],
        },
        "double_chance_12": {
            "n": dc12["n"],
            "challenger": dc12["challenger"],
            "poisson": dc12["poisson"],
            "delta_brier": dc12["delta_brier"],
            "delta_log_loss": dc12["delta_log_loss"],
            "blocker": dc12["blocker"],
            "status": dc12["status"],
        },
        "oos": {
            "current": oos["current_oos_observations"],
            "target": oos["target_oos_observations"],
            "remaining": oos["remaining_to_1000"],
            "metrics_opened": oos["metrics_opened"],
        },
        "adjudication": {
            "signal_authorized_markets": ["OVER_2_5"],
            "calibrated_measured_not_signal_promoted": ["MATCH_RESULT_1X2", "UNDER_2_5", "DOUBLE_CHANCE_1X", "DOUBLE_CHANCE_X2"],
            "research_walk_forward_measured": [
                "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
                "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
                "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
                "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
                "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
                "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
            ],
            "prospective_count_ready_but_no_dedicated_metric_artifact": ["TEAM_TOTAL_GOALS_HOME", "TEAM_TOTAL_GOALS_AWAY"],
            "not_promotable": ["DOUBLE_CHANCE_12"],
        },
    }

def main():
    out = ROOT / "evidence/governance/MATRIX_42_MARKET_ELITE_CALIBRATION_CLOSURE_28OCT2026.json"
    out.write_text(json.dumps(build_report(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
