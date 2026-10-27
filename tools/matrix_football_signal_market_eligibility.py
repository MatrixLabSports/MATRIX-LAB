from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path("evidence/api_football")
OUT=ROOT/"governance/MATRIX_FOOTBALL_SIGNAL_MARKET_ELIGIBILITY_LAST.json"

def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v

def lane_state(path:str)->dict[str,Any]:
    p=Path(path)
    return load(p) if p.exists() else {}

def build()->dict[str,Any]:
    over=load(ROOT/"governance/over_2_5_p_matrix_promotion.json")
    oos=load(ROOT/"calibration_v2/OOS_4001_5000_STATE.json")
    dc12=load(ROOT/"calibration_v2/lanes/double_chance_12/state.json")
    btts=load(ROOT/"calibration_v2/lanes/btts/state.json")
    tsh=load(ROOT/"promoted_team_markets/team_total_shots_home/state.json")
    tsa=load(ROOT/"promoted_team_markets/team_total_shots_away/state.json")
    fouls=load(ROOT/"promoted_team_markets/team_fouls_total/state.json")
    pshots=load(ROOT/"player_shots_v3_prospective/state.json")
    failed=load(ROOT/"market_expansion/failed_team_markets_v3/summary.json")
    oos_current=int(oos.get("current_oos_observations") or 0)
    oos_remaining=int(oos.get("remaining_to_1000") or 0)

    markets={
      "OVER_2_5":{
        "signal_eligible": bool(over.get("promotion_status")=="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"),
        "status":"PROMOTED_SIGNAL_ONLY",
        "telegram_adapter_status":"IMPLEMENTED",
        "evidence":"evidence/api_football/governance/over_2_5_p_matrix_promotion.json",
      },
      "UNDER_2_5":{
        "signal_eligible":False,
        "status":"BLOCKED_UNTIL_OOS1000_ADJUDICATION",
        "derived_from":"OVER_2_5",
        "oos_progress":oos_current,
        "oos_remaining":oos_remaining,
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "1X2":{
        "signal_eligible":False,
        "status":"BLOCKED_UNTIL_OOS1000_ADJUDICATION",
        "oos_progress":oos_current,
        "oos_remaining":oos_remaining,
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "DOUBLE_CHANCE_1X":{
        "signal_eligible":False,
        "status":"BLOCKED_UNTIL_OOS1000_ADJUDICATION",
        "derived_from":"1X2",
        "oos_progress":oos_current,
        "oos_remaining":oos_remaining,
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "DOUBLE_CHANCE_X2":{
        "signal_eligible":False,
        "status":"BLOCKED_UNTIL_OOS1000_ADJUDICATION",
        "derived_from":"1X2",
        "oos_progress":oos_current,
        "oos_remaining":oos_remaining,
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "DOUBLE_CHANCE_12":{
        "signal_eligible":False,
        "status":str(dc12.get("status") or "BLOCKED_NOT_PROMOTED"),
        "blocker":dc12.get("blocker"),
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "BTTS":{
        "signal_eligible":False,
        "status":str(btts.get("status") or "BLOCKED_NEW_CHALLENGER_REQUIRED"),
        "blocker":btts.get("blocker"),
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "TEAM_TOTAL_SHOTS_HOME":{
        "signal_eligible":False,
        "status":"PROSPECTIVE_VALIDATION_NOT_SIGNAL_ELIGIBLE",
        "prospective_freezes":int(tsh.get("freeze_observation_count") or 0),
        "remaining_to_first_gate":int(((tsh.get("gates") or {}).get("30") or {}).get("remaining") or 30),
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "TEAM_TOTAL_SHOTS_AWAY":{
        "signal_eligible":False,
        "status":"PROSPECTIVE_VALIDATION_NOT_SIGNAL_ELIGIBLE",
        "prospective_freezes":int(tsa.get("freeze_observation_count") or 0),
        "remaining_to_first_gate":int(((tsa.get("gates") or {}).get("30") or {}).get("remaining") or 30),
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "TEAM_FOULS_TOTAL":{
        "signal_eligible":False,
        "status":"PROSPECTIVE_VALIDATION_NOT_SIGNAL_ELIGIBLE",
        "prospective_freezes":int(fouls.get("freeze_observation_count") or 0),
        "remaining_to_first_gate":int(((fouls.get("gates") or {}).get("30") or {}).get("remaining") or 30),
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "PLAYER_SHOTS":{
        "signal_eligible":False,
        "status":"PROSPECTIVE_VALIDATION_NOT_SIGNAL_ELIGIBLE",
        "prospective_freezes":int(pshots.get("freeze_observation_count") or 0),
        "remaining_to_first_gate":int(((pshots.get("gates") or {}).get("30") or {}).get("remaining") or 30),
        "external_dependency":"PREMATCH_LINEUP_AND_CANONICAL_LINE",
        "telegram_adapter_status":"PENDING_AFTER_PROMOTION",
      },
      "CORNERS":{
        "signal_eligible":False,
        "status":"NO_GO_HISTORICAL_OOS_V3",
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "TEAM_SHOTS_ON_TARGET":{
        "signal_eligible":False,
        "status":"NO_GO_HISTORICAL_OOS_V3",
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "TEAM_GOALKEEPER_SAVES":{
        "signal_eligible":False,
        "status":"NO_GO_HISTORICAL_OOS_V3",
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "TEAM_YELLOW_CARDS":{
        "signal_eligible":False,
        "status":"NO_GO_HISTORICAL_OOS_V3",
        "telegram_adapter_status":"NOT_AUTHORIZED",
      },
      "FIRST_HALF_GOALS":{
        "signal_eligible":False,
        "status":"NOT_IMPLEMENTED_NO_CALIBRATED_LANE_FOUND",
        "telegram_adapter_status":"NOT_IMPLEMENTED",
      },
      "SECOND_HALF_GOALS":{
        "signal_eligible":False,
        "status":"NOT_IMPLEMENTED_NO_CALIBRATED_LANE_FOUND",
        "telegram_adapter_status":"NOT_IMPLEMENTED",
      },
    }
    eligible=[k for k,v in markets.items() if v["signal_eligible"]]
    return {
      "schema":"MATRIX_FOOTBALL_SIGNAL_MARKET_ELIGIBILITY_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":"PASS",
      "signal_eligible_markets":eligible,
      "signal_eligible_market_count":len(eligible),
      "markets":markets,
      "root_cause_of_missing_other_market_signals":{
        "current_telegram_football_adapter_market":"OVER_2_5_ONLY",
        "other_markets_not_authorized_for_signal_generation":True,
        "core_market_promotion_waits_for_oos1000":True,
        "markets_with_no_implemented_calibrated_lane":["FIRST_HALF_GOALS","SECOND_HALF_GOALS"],
      },
      "protections":{
        "no_automatic_promotion":True,
        "odds_do_not_generate_p_matrix":True,
        "missing_not_zero":True,
        "no_silent_imputation":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      }
    }

def main():
    result=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":result["status"],
      "eligible":result["signal_eligible_markets"],
      "eligible_count":result["signal_eligible_market_count"],
      "oos_progress":result["markets"]["1X2"]["oos_progress"],
      "oos_remaining":result["markets"]["1X2"]["oos_remaining"],
    },sort_keys=True))

if __name__=="__main__":
    main()
