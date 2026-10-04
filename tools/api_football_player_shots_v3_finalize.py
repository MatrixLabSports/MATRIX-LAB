from __future__ import annotations
import json
from pathlib import Path

GATES=(30,50,100,200)

def main()->None:
    src=Path("evidence/api_football/market_expansion/player_shots_lineup_role_v3")
    model_path=src/"model.json"
    progress_path=src/"acquisition_progress.json"
    if not progress_path.exists():
        raise SystemExit("PLAYER_SHOTS_V3_ACQUISITION_PROGRESS_MISSING")
    progress=json.loads(progress_path.read_text(encoding="utf-8"))
    out=Path("evidence/api_football/player_shots_v3_prospective")
    out.mkdir(parents=True,exist_ok=True)
    for name in ("freeze_ledger.jsonl","calibration_ledger.jsonl"):
        p=out/name
        if not p.exists(): p.write_text("",encoding="utf-8")
    if progress.get("status")!="COMPLETE_MODEL_EVALUATED" or not model_path.exists():
        state={
          "schema":"MATRIX_PLAYER_SHOTS_V3_PROSPECTIVE_STATE_V1",
          "status":"BLOCKED_REBUILD_INCOMPLETE",
          "acquisition_cached":progress.get("cached_lineup_count",0),
          "acquisition_target":progress.get("fixture_target_count"),
          "prospective_lane_ready":False,
          "freeze_observation_count":0,
          "calibration_observation_count":0,
          "gates":{str(g):{"threshold":g,"status":"SEALED","metrics_opened":False,"remaining":g} for g in GATES},
          "automatic_wagering":False,"real_money":"BLOCKED"
        }
    else:
        model=json.loads(model_path.read_text(encoding="utf-8"))
        eligible=bool(model.get("prospective_freeze_allowed"))
        state={
          "schema":"MATRIX_PLAYER_SHOTS_V3_PROSPECTIVE_STATE_V1",
          "status":"ACTIVE_WAITING_PREMATCH_LINEUP_AND_LINE" if eligible else "NO_GO_HISTORICAL_OOS_V3",
          "prospective_lane_ready":eligible,
          "model_status":model.get("status"),
          "model_selected_parameters_sha256":model.get("selected_parameters_sha256"),
          "historical_role_source":"/fixtures/lineups",
          "prospective_role_source":"/fixtures/lineups",
          "freeze_observation_count":0,
          "calibration_observation_count":0,
          "gates":{str(g):{"threshold":g,"status":"SEALED","metrics_opened":False,"remaining":g} for g in GATES},
          "parameter_tuning_allowed":False,
          "automatic_wagering":False,"real_money":"BLOCKED"
        }
    (out/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":state["status"],"ready":state["prospective_lane_ready"],"real_money":"BLOCKED"},sort_keys=True))

if __name__=="__main__":
    main()
