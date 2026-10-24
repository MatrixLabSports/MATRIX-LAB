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
OUT=Path("evidence/market_portfolio/MATRIX_42_LANE_ZERO_PROSPECTIVE_BLOCKERS_LAST.json")

TENNIS_LIVE_ONLY={
 "SET_WINNER","SET_HANDICAP","TOTAL_SETS","BOTH_PLAYERS_WIN_SET",
 "GAME_HANDICAP","TOTAL_GAMES","PLAYER_TOTAL_GAMES","TIEBREAK_YES_NO",
}
TENNIS_SERVE={"ACES","DOUBLE_FAULTS","BREAKS_OF_SERVE"}
PRIORITY_LANES={"TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY","ASIAN_OR_EUROPEAN_HANDICAP"}
TEAM_SHOTS={"TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY"}
EXTENDED_FOOTBALL={
 "CORNERS_OVER_UNDER","CARDS_OVER_UNDER","TEAM_SHOTS_ON_TARGET_HOME","TEAM_SHOTS_ON_TARGET_AWAY",
 "TEAM_FOULS_HOME","TEAM_FOULS_AWAY","GOALKEEPER_SAVES","PLAYER_SHOTS_ON_TARGET",
 "PLAYER_ASSISTS","PLAYER_PASSES","PLAYER_TACKLES","PLAYER_FOULS",
}


def _load(path:Path)->dict[str,Any]:
    if not path.exists():
        return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value,dict) else {}


def build(generated_at:datetime|None=None)->dict[str,Any]:
    reg=_load(REGISTRY); priority=_load(PRIORITY); promoted=_load(PROMOTED); player=_load(PLAYER); serve=_load(SERVE)
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
            reason="NO_CANONICAL_TARGET_MARKET_OFFERS_IN_CHECKED_EVENTS"
            evidence.append(PROMOTED.as_posix())
        elif lane=="PLAYER_SHOTS":
            reason="PREMATCH_LINEUP_NOT_AVAILABLE_IN_CHECKED_EVENTS"
            evidence.append(PLAYER.as_posix())
        elif lane=="BTTS":
            reason="BTTS_CANDIDATES_REJECTED_NOT_APPROVED_FOR_PROSPECTIVE_BRIDGE"
            evidence.extend([
              "evidence/api_football/btts_challenger_v2/manifest.json",
              "evidence/api_football/btts_challenger_v3/manifest.json",
            ])
        elif lane in EXTENDED_FOOTBALL:
            reason="COVERAGE_IMPLEMENTATION_PRESENT_BUT_NO_GOVERNED_PREMATCH_PREDICTIVE_FREEZE"
            evidence.append("tools/api_football_extended_market_coverage_probe.py")
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
