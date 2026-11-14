from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("evidence/api_football")
OUT=ROOT/"governance/MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json"
CHECKPOINT=ROOT/"calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json"
OOS=ROOT/"calibration_v2/OOS_4001_5000_STATE.json"
LANE=ROOT/"calibration_v2/lanes/double_chance_1x/state.json"
P_MATRIX=ROOT/"governance/double_chance_1x_p_matrix_promotion.json"
QUOTE=ROOT/"governance/double_chance_1x_execution_quote_contract.json"
ENGINE=Path("tools/telegram_double_chance_1x_signal_engine.py")

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def build():
    cpdoc=load(CHECKPOINT); oos=load(OOS); lane=load(LANE)
    cp=(cpdoc.get("markets") or {}).get("double_chance_1x") or {}
    target=int(oos.get("target_oos_observations") or 1000)
    current=int(oos.get("current_oos_observations") or 0)
    checks={
      "checkpoint_4000_complete": cp.get("eligible_rows")==4000 and cp.get("missing_rows")==0,
      "checkpoint_not_automatic_promotion": (cpdoc.get("adjudication") or {}).get("market_promotion")=="NOT_AUTOMATICALLY_AUTHORIZED",
      "derived_from_1x2_declared": cp.get("derived_from")=="1X2",
      "lane_no_backfill": lane.get("no_backfill") is True,
      "lane_parameters_frozen": lane.get("parameter_tuning_allowed") is False,
      "odds_not_used_for_probability": (cpdoc.get("governance") or {}).get("odds_used_to_generate_probability") is False,
      "oos_target_reached": current>=target,
      "oos_metrics_opened": oos.get("metrics_opened") is True,
      "oos_outcomes_read": int(oos.get("outcomes_read_for_oos_metrics") or 0)>=target,
      "explicit_signal_promotion_exists": P_MATRIX.exists(),
      "dedicated_quote_path_certified": QUOTE.exists(),
      "telegram_signal_engine_certified": ENGINE.exists()
    }
    blockers=[]
    if not checks["oos_target_reached"]: blockers.append("OOS_4001_5000_NOT_COMPLETE")
    if not checks["oos_metrics_opened"] or not checks["oos_outcomes_read"]: blockers.append("OOS_1000_METRICS_NOT_OPENED")
    if not checks["explicit_signal_promotion_exists"]: blockers.append("NO_EXPLICIT_GOVERNED_DOUBLE_CHANCE_1X_P_MATRIX_PROMOTION")
    if not checks["dedicated_quote_path_certified"]: blockers.append("NO_DEDICATED_DOUBLE_CHANCE_1X_QUOTE_REVALIDATION_CONTRACT")
    if not checks["telegram_signal_engine_certified"]: blockers.append("NO_DOUBLE_CHANCE_1X_TELEGRAM_SIGNAL_ENGINE")
    ok=all(checks.values())
    return {
      "schema":"MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "market":"DOUBLE_CHANCE_1X",
      "status":"PASS_PROMOTION_READY" if ok else "BLOCKED_NOT_PROMOTABLE",
      "promotion_allowed":ok,
      "signal_status":"SIGNAL_AUTHORIZED" if ok else "RESEARCH_ONLY",
      "checks":checks,
      "blockers":blockers,
      "physical_state":{
        "checkpoint_calibration_rows":cp.get("eligible_rows"),
        "checkpoint_brier_score":(cp.get("metrics") or {}).get("brier_score"),
        "checkpoint_log_loss":(cp.get("metrics") or {}).get("log_loss"),
        "checkpoint_ece":(cp.get("metrics") or {}).get("ece"),
        "checkpoint_mean_predicted_probability":(cp.get("metrics") or {}).get("mean_predicted_probability"),
        "checkpoint_observed_positive_rate":(cp.get("metrics") or {}).get("observed_positive_rate"),
        "lane_settlement_count":lane.get("settlement_count"),
        "lane_pending_settlement_count":lane.get("pending_settlement_count"),
        "lane_freeze_observation_count":lane.get("freeze_observation_count"),
        "oos_current_observations":current,
        "oos_target_observations":target,
        "oos_remaining":max(0,target-current),
        "oos_metrics_opened":oos.get("metrics_opened")
      },
      "governance":{
        "next_required_action":"COMPLETE_PREREGISTERED_OOS_1000_WITHOUT_TUNING_THEN_EVALUATE_DOUBLE_CHANCE_1X_SEPARATELY",
        "minimum_decimal_odds_exclusive":1.5,
        "positive_ev_required":True,
        "p_matrix_must_exist_before_odds":True,
        "odds_may_not_generate_probability":True,
        "no_backfill":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "promotion_before_all_gates":"FORBIDDEN"
      }
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"promotion_allowed":out["promotion_allowed"],"blockers":out["blockers"]},sort_keys=True))

if __name__=="__main__":
    main()
