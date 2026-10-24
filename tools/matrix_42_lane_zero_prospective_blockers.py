from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REGISTRY=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
PRIORITY=Path("evidence/api_football/market_expansion/priority_market_lab_last.json")
PROMOTED=Path("evidence/api_football/promoted_team_markets/last_run.json")
PLAYER=Path("evidence/api_football/player_shots_v3_prospective/last_run.json")
SERVE=Path("evidence/tennis_serve_stats_lab/MATRIX_TENNIS_SERVE_STATS_LAB_LAST.json")
TEAM_MODELS_V3=Path("evidence/api_football/market_expansion/failed_team_markets_v3/summary.json")
TEAM_SHOTS_MODELS=Path("evidence/api_football/market_expansion/team_total_shots_side_models/summary.json")
PLAYER_MODELS=Path("evidence/api_football/market_expansion/player_models/summary.json")
OUT=Path("evidence/market_portfolio/MATRIX_42_LANE_ZERO_PROSPECTIVE_BLOCKERS_LAST.json")

TENNIS_LIVE_ONLY={
 "SET_WINNER","SET_HANDICAP","TOTAL_SETS","BOTH_PLAYERS_WIN_SET",
 "GAME_HANDICAP","TOTAL_GAMES","PLAYER_TOTAL_GAMES","TIEBREAK_YES_NO",
}
TENNIS_SERVE={"ACES","DOUBLE_FAULTS","BREAKS_OF_SERVE"}
PRIORITY_LANES={"TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY","ASIAN_OR_EUROPEAN_HANDICAP"}
TEAM_SHOTS={"TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY"}
REJECTED_TEAM_V3={
 "CORNERS_OVER_UNDER":"CORNERS",
 "CARDS_OVER_UNDER":"TEAM_YELLOW_CARDS",
 "TEAM_SHOTS_ON_TARGET_HOME":"TEAM_SHOTS_ON_TARGET",
 "TEAM_SHOTS_ON_TARGET_AWAY":"TEAM_SHOTS_ON_TARGET",
 "GOALKEEPER_SAVES":"TEAM_GOALKEEPER_SAVES",
}
REJECTED_PLAYER={
 "PLAYER_SHOTS_ON_TARGET":"PLAYER_SHOTS_ON_TARGET",
 "PLAYER_ASSISTS":"PLAYER_ASSISTS",
 "PLAYER_PASSES":"PLAYER_PASSES",
 "PLAYER_TACKLES":"PLAYER_TACKLES",
 "PLAYER_FOULS":"PLAYER_FOULS",
}


def _load(path:Path)->dict[str,Any]:
    if not path.exists():
        return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value,dict) else {}


def build(generated_at:datetime|None=None)->dict[str,Any]:
    reg=_load(REGISTRY); priority=_load(PRIORITY); promoted=_load(PROMOTED); player=_load(PLAYER); serve=_load(SERVE)
    team_v3=_load(TEAM_MODELS_V3); team_shots_models=_load(TEAM_SHOTS_MODELS); player_models=_load(PLAYER_MODELS)
    if reg.get("status")!="PASS" or reg.get("total_lanes")!=42:
        raise ValueError("PROSPECTIVE_REGISTRY_NOT_PASS")
    rows=[]
    for lane,state in sorted((reg.get("lanes") or {}).items()):
        if not isinstance(state,Mapping) or int(state.get("prospective_unique_count") or 0)>0:
            continue
        reason="NO_VALID_GOVERNED_PREMATCH_FREEZE_FOUND"
        evidence=[]
        if lane in TENNIS_SERVE:
            reason="INPLAY_SOURCE_COVERAGE_ONLY_NO_PREMATCH_PREDICTIVE_FREEZE"
            evidence.append(SERVE.as_posix())
        elif lane in TENNIS_LIVE_ONLY:
            reason="LIVE_FEATURE_IMPLEMENTATION_HAS_NO_GOVERNED_PREMATCH_FREEZE_PRODUCER"
            evidence.append("tools/live_tennis_feature_extractor.py")
        elif lane in PRIORITY_LANES:
            reason="PRIORITY_LAB_PROBABILITY_NOT_GENERATED"
            evidence.append(PRIORITY.as_posix())
        elif lane in TEAM_SHOTS:
            side="HOME" if lane.endswith("_HOME") else "AWAY"
            model=((team_shots_models.get("lanes") or {}).get(side) or {})
            if model.get("prospective_eligible") is True:
                reason="MODEL_FROZEN_PROSPECTIVE_ELIGIBLE_BUT_NO_CANONICAL_PREMATCH_OFFER"
            else:
                reason="TEAM_TOTAL_SHOTS_MODEL_NOT_PROSPECTIVE_ELIGIBLE"
            evidence.extend([TEAM_SHOTS_MODELS.as_posix(),PROMOTED.as_posix()])
        elif lane in {"TEAM_FOULS_HOME","TEAM_FOULS_AWAY"}:
            model=((team_v3.get("lanes") or {}).get("TEAM_FOULS") or {})
            if model.get("prospective_eligible") is True:
                reason="TEAM_FOULS_V3_MODEL_ELIGIBLE_BUT_CANONICAL_HOME_AWAY_FREEZE_NOT_AVAILABLE"
            else:
                reason="TEAM_FOULS_MODEL_REJECTED"
            evidence.extend([TEAM_MODELS_V3.as_posix(),PROMOTED.as_posix()])
        elif lane=="PLAYER_SHOTS":
            reason="PLAYER_SHOTS_V3_MODEL_ELIGIBLE_BUT_PREMATCH_LINEUP_NOT_AVAILABLE"
            evidence.extend([
              "evidence/api_football/market_expansion/player_shots_lineup_role_v3/summary.json",
              PLAYER.as_posix(),
            ])
        elif lane=="BTTS":
            reason="BTTS_CANDIDATES_REJECTED_NOT_APPROVED_FOR_PROSPECTIVE_BRIDGE"
            evidence.extend([
              "evidence/api_football/btts_challenger_v2/manifest.json",
              "evidence/api_football/btts_challenger_v3/manifest.json",
            ])
        elif lane in REJECTED_TEAM_V3:
            model_key=REJECTED_TEAM_V3[lane]
            model=((team_v3.get("lanes") or {}).get(model_key) or {})
            reason="MODEL_REJECTED_HISTORICAL_OOS_V3" if model.get("prospective_eligible") is False else "NO_GOVERNED_PREMATCH_FREEZE"
            evidence.append(TEAM_MODELS_V3.as_posix())
        elif lane in REJECTED_PLAYER:
            model_key=REJECTED_PLAYER[lane]
            model=((player_models.get("lanes") or {}).get(model_key) or {})
            reason="PLAYER_MODEL_REJECTED_HISTORICAL_OOS" if model.get("historical_candidate_passed") is False else "PLAYER_MODEL_PROSPECTIVE_BLOCKED"
            evidence.append(PLAYER_MODELS.as_posix())
        rows.append({
            "market_lane":lane,
            "sport":state.get("sport"),
            "operational_state":state.get("operational_state"),
            "prospective_unique_count":0,
            "blocker":reason,
            "evidence":evidence,
            "must_continue_collecting":True,
            "production_authorized":False,
        })
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
      "schema":"MATRIX_42_LANE_ZERO_PROSPECTIVE_BLOCKERS_V1",
      "generated_at_utc":now,
      "status":"PASS",
      "zero_prospective_lane_count":len(rows),
      "rows":rows,
      "source_checks":{
        "priority_lab_status":priority.get("status"),
        "priority_probability_not_generated_count":sum(1 for x in priority.get("rows") or [] if isinstance(x,Mapping) and x.get("probability_status")=="NOT_GENERATED"),
        "promoted_zero_freeze_reason":(promoted.get("offer_audit") or {}).get("zero_freeze_reason"),
        "player_shots_future_events_checked":player.get("future_events_checked"),
        "player_shots_blocker_count":len(player.get("blockers") or []),
        "tennis_serve_status":serve.get("status"),
        "tennis_serve_provider_mode":"INPLAY_SOURCE_COVERAGE",
        "team_total_shots_home_model_status":((team_shots_models.get("lanes") or {}).get("HOME") or {}).get("status"),
        "team_total_shots_away_model_status":((team_shots_models.get("lanes") or {}).get("AWAY") or {}).get("status"),
        "team_fouls_v3_model_status":((team_v3.get("lanes") or {}).get("TEAM_FOULS") or {}).get("status"),
        "player_shots_v3_model_status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION_V3",
      },
      "policy":{
        "no_fake_backfill":True,
        "no_silent_imputation":True,
        "odds_do_not_generate_probability":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      },
    }


def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--out",default=str(OUT)); a=p.parse_args()
    result=build()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"zero_prospective_lane_count":result["zero_prospective_lane_count"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
