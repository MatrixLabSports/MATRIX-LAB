from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
SUPERVISOR=ROOT/"evidence"/"market_portfolio"/"MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"
REGISTRY=ROOT/"evidence"/"market_portfolio"/"MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
CALIBRATION=ROOT/"evidence"/"governance"/"MATRIX_42_MARKET_ELITE_CALIBRATION_CLOSURE_28OCT2026.json"
OUT=ROOT/"evidence"/"governance"/"MATRIX_42_MARKET_ACTIVATION_LAST.json"

FOOTBALL=[
"MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12",
"TOTAL_GOALS_OVER_UNDER","TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY",
"FIRST_HALF_TOTAL_GOALS_OVER_UNDER","SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
"FIRST_HALF_TEAM_TOTAL_GOALS_HOME","FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
"SECOND_HALF_TEAM_TOTAL_GOALS_HOME","SECOND_HALF_TEAM_TOTAL_GOALS_AWAY","BTTS",
"ASIAN_OR_EUROPEAN_HANDICAP","CORNERS_OVER_UNDER","CARDS_OVER_UNDER",
"TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY","TEAM_SHOTS_ON_TARGET_HOME",
"TEAM_SHOTS_ON_TARGET_AWAY","TEAM_FOULS_HOME","TEAM_FOULS_AWAY","GOALKEEPER_SAVES",
"PLAYER_SHOTS","PLAYER_SHOTS_ON_TARGET","PLAYER_ASSISTS","PLAYER_PASSES",
"PLAYER_TACKLES","PLAYER_FOULS"]
TENNIS=[
"MATCH_WINNER","SET_WINNER","SET_HANDICAP","TOTAL_SETS","BOTH_PLAYERS_WIN_SET",
"GAME_HANDICAP","TOTAL_GAMES","PLAYER_TOTAL_GAMES","TIEBREAK_YES_NO","ACES",
"DOUBLE_FAULTS","BREAKS_OF_SERVE"]
CANONICAL=FOOTBALL+TENNIS
PERIOD_KEYS={
"FIRST_HALF_TOTAL_GOALS_OVER_UNDER","SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
"FIRST_HALF_TEAM_TOTAL_GOALS_HOME","FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
"SECOND_HALF_TEAM_TOTAL_GOALS_HOME","SECOND_HALF_TEAM_TOTAL_GOALS_AWAY"}

def _load(path:Path)->dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def classify(supervisor_row:dict[str,Any], registry_row:dict[str,Any], calibration:dict[str,Any])->tuple[str,int,bool,str|None]:
    key=supervisor_row["market_key"]
    count=int(registry_row.get("prospective_unique_count") or 0)
    price=str(supervisor_row.get("price_state") or "")
    adjud=calibration.get("adjudication") or {}
    if key=="TOTAL_GOALS_OVER_UNDER":
        return "ACTIVE_GOVERNED_SELECTION_ONLY",0,True,"ONLY_OVER_2_5"
    if key=="MATCH_WINNER":
        price_ready=price in {"PRICE_FAMILY_OBSERVED","PRICE_MAPPING_OBSERVED","EXACT_PRICE_OBSERVED"}
        return "ACTIVE_MODEL_READY" if price_ready else "ACTIVE_MODEL_PRICE_MAPPING_REQUIRED",1,price_ready,"MATCH_WINNER"
    if key in set(adjud.get("not_promotable") or []):
        return "NOT_PROMOTABLE_DIAGNOSTIC_ONLY",7,False,None
    if key in PERIOD_KEYS:
        return "MEASURED_PRICE_AND_PROMOTION_REQUIRED",2,False,None
    if key in {"MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2"}:
        return "MEASURED_PROMOTION_REQUIRED",2,False,None
    if key in set(adjud.get("pending_dedicated_calibration") or []):
        return "DEDICATED_CALIBRATION_REQUIRED",3,False,None
    if 0<count<100:
        return "PROSPECTIVE_COLLECTION_LOW_COUNT",4,False,None
    if count==0 and price=="PRICE_FAMILY_OBSERVED":
        return "PROSPECTIVE_COLLECTION_REQUIRED_PRICE_OBSERVED",5,False,None
    if count==0:
        return "PROSPECTIVE_AND_PRICE_MAPPING_REQUIRED",6,False,None
    return "LAB_REVIEW_REQUIRED",5,False,None

def build()->dict[str,Any]:
    s=_load(SUPERVISOR); r=_load(REGISTRY); c=_load(CALIBRATION)
    rows_by_key={x["market_key"]:x for x in s.get("rows",[])}
    if set(rows_by_key)!=set(CANONICAL):
        missing=sorted(set(CANONICAL)-set(rows_by_key)); extra=sorted(set(rows_by_key)-set(CANONICAL))
        raise RuntimeError(f"CANONICAL_42_MISMATCH missing={missing} extra={extra}")
    if len(CANONICAL)!=42 or len(FOOTBALL)!=30 or len(TENNIS)!=12:
        raise RuntimeError("CANONICAL_COUNTS_INVALID")
    lanes=[]
    for key in CANONICAL:
        sr=rows_by_key[key]
        rr=(r.get("lanes") or {}).get(key,{})
        cls,priority,telegram_ready,selection=classify(sr,rr,c)
        lanes.append({
            "market_key":key,
            "display_name":sr.get("display_name"),
            "sport":sr.get("sport"),
            "operational_state":sr.get("operational_state"),
            "production_authorized_by_supervisor":bool(sr.get("production_authorized")),
            "price_state":sr.get("price_state"),
            "supervisor_blockers":sr.get("blockers") or [],
            "prospective_unique_count":int(rr.get("prospective_unique_count") or 0),
            "gate_600_reached":int(rr.get("prospective_unique_count") or 0)>=600,
            "activation_class":cls,
            "activation_priority":priority,
            "telegram_market_ready":telegram_ready,
            "telegram_selection_scope":selection,
            "must_continue_collecting":True
        })
    counts={}
    for x in lanes: counts[x["activation_class"]]=counts.get(x["activation_class"],0)+1
    return {
        "schema":"MATRIX_42_MARKET_ACTIVATION_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_generated_at_utc":{
            "supervisor":s.get("generated_at_utc"),"registry":r.get("generated_at_utc")
        },
        "governance":{
            "total_lanes":42,"football_lanes":30,"tennis_lanes":12,
            "source_order":["SOFASCORE","FLASHSCORE","APIS"],
            "cadence_minutes":15,"real_money":"BLOCKED","automatic_wagering":False,
            "missing_is_not_zero":True,"post_start_backfill_forbidden":True,
            "gate_600_does_not_auto_promote":True,"zero_picks_valid":True,
            "productive_odds_strictly_greater_than":1.50,
            "productive_min_p_matrix":0.60,"productive_min_revalidated_ev":0.05,
            "ev_0_to_5pct":"SHADOW_LAB_ONLY","max_approx_markets_per_match":3
        },
        "counts":{
            "supervisor_states":s.get("state_counts"),
            "lanes_at_600":(r.get("counts") or {}).get("lanes_at_600"),
            "lanes_with_any_valid_prospective":(r.get("counts") or {}).get("lanes_with_any_valid_prospective"),
            "ledger_rows_total":(r.get("counts") or {}).get("ledger_rows_total"),
            "activation_classes":counts
        },
        "telegram":{
            "ready_market_families":[x["market_key"] for x in lanes if x["telegram_market_ready"]],
            "hard_rule":"A lane being ACTIVE or >=600 does not bypass exact price, EV, calibration, promotion, risk or freshness gates."
        },
        "lanes":sorted(lanes,key=lambda x:(x["activation_priority"],x["market_key"]))
    }

def telegram_market_allowed(market_key:str, selection:str, p_matrix:float, decimal_odds:float, ev:float)->bool:
    state=build()
    lane=next((x for x in state["lanes"] if x["market_key"]==market_key),None)
    if not lane or not lane["telegram_market_ready"]:
        return False
    if float(p_matrix)<0.60 or float(decimal_odds)<=1.50 or float(ev)<0.05:
        return False
    if market_key=="TOTAL_GOALS_OVER_UNDER" and selection!="OVER_2_5":
        return False
    return True

def main()->None:
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","lanes":len(out["lanes"]),"counts":out["counts"],"telegram":out["telegram"]},ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
