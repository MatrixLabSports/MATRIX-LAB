from __future__ import annotations
import json
from pathlib import Path
from typing import Any

GATES=(30,50,100,200)

LANES={
 "TEAM_TOTAL_SHOTS_HOME":{
   "model":"evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json",
   "bet_id":221,"bet_name":"Shots. Home Total",
 },
 "TEAM_TOTAL_SHOTS_AWAY":{
   "model":"evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json",
   "bet_id":220,"bet_name":"Shots. Away Total",
 },
 "TEAM_FOULS_TOTAL":{
   "model":"evidence/api_football/market_expansion/failed_team_markets_v3/team_fouls_model_v3.json",
   "bet_id":173,"bet_name":"Fouls. Total",
 },
}

def _load(path:str)->dict[str,Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _state(lane:str,cfg:dict[str,Any],model:dict[str,Any],catalog:dict[str,Any])->dict[str,Any]:
    eligible=bool(model.get("prospective_eligible"))
    available=any(int(x.get("id"))==cfg["bet_id"] for vals in catalog.get("matches",{}).values() for x in vals if x.get("id") is not None)
    count=0
    gates={str(g):{"threshold":g,"status":"SEALED","observations_available":count,"remaining":g,"metrics_opened":False} for g in GATES}
    ready=eligible and available
    return {
      "schema":"MATRIX_PROMOTED_TEAM_MARKET_PROSPECTIVE_STATE_V1",
      "lane":lane,"market_binding":{"api_football_bet_id":cfg["bet_id"],"api_football_bet_name":cfg["bet_name"]},
      "model_status":model.get("status"),"model_parameters_sha256":model.get("model_parameters_sha256"),
      "historical_oos_passed":eligible,"official_market_binding_verified":available,
      "prospective_lane_ready":ready,
      "status":"ACTIVE_WAITING_CANONICAL_PREMATCH_LINE_AND_CURRENT_PIT_FEATURES" if ready else "BLOCKED_MODEL_OR_MARKET_BINDING",
      "freeze_observation_count":0,"calibration_observation_count":0,
      "gates":gates,"metrics_policy":"SEALED_UNTIL_EACH_THRESHOLD_30_50_100_200",
      "current_pit_features_required":True,"canonical_prematch_line_required":True,
      "parameter_tuning_allowed":False,"odds_used_to_generate_probability":False,
      "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main()->None:
    catalog=_load("evidence/api_football/market_expansion/market_binding_catalog.json")
    root=Path("evidence/api_football/promoted_team_markets"); root.mkdir(parents=True,exist_ok=True)
    summary={}
    for lane,cfg in LANES.items():
        model=_load(cfg["model"])
        slug=lane.casefold()
        out=root/slug; out.mkdir(parents=True,exist_ok=True)
        for name in ("freeze_ledger.jsonl","calibration_ledger.jsonl"):
            p=out/name
            if not p.exists(): p.write_text("",encoding="utf-8")
        state=_state(lane,cfg,model,catalog)
        (out/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        summary[lane]={"status":state["status"],"prospective_lane_ready":state["prospective_lane_ready"],"bet_id":cfg["bet_id"],"freeze_observation_count":0,"gate_30":"SEALED"}
    master={"schema":"MATRIX_PROMOTED_TEAM_MARKETS_PROSPECTIVE_SUMMARY_V1","lanes":summary,"automatic_wagering":False,"real_money":"BLOCKED"}
    (root/"summary.json").write_text(json.dumps(master,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(master,sort_keys=True))

if __name__=="__main__":
    main()
