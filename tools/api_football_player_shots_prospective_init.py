from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

GATES=(30,50,100,200)

def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value

def build_state(cert_pointer:dict[str,Any],model:dict[str,Any])->dict[str,Any]:
    certified=bool(cert_pointer.get("prospective_freeze_allowed"))
    count=0
    gates={
        str(x):{
            "threshold":x,
            "status":"SEALED" if count<x else "OPENED",
            "observations_available":count,
            "remaining":max(0,x-count),
            "metrics_opened":False,
        }
        for x in GATES
    }
    return {
        "schema":"MATRIX_PLAYER_SHOTS_PROSPECTIVE_STATE_V1",
        "lane":"PLAYER_SHOTS_OVER_1_5",
        "evaluation_line":float(model["evaluation_line"]),
        "model_selected_parameters_sha256":model["selected_parameters_sha256"],
        "role_source_certification_manifest_sha256":cert_pointer.get("manifest_sha256"),
        "cross_source_role_equivalence_certified":bool(cert_pointer.get("cross_source_role_equivalence_certified")),
        "expected_minutes_pit_prospective_certified":bool(cert_pointer.get("expected_minutes_pit_prospective_certified")),
        "prospective_freeze_allowed":certified,
        "status":"ACTIVE_WAITING_FIRST_PREMATCH_FREEZE" if certified else "BLOCKED_SOURCE_CERTIFICATION",
        "freeze_observation_count":count,
        "calibration_observation_count":0,
        "gates":gates,
        "metrics_policy":"SEALED_UNTIL_EACH_THRESHOLD_30_50_100_200",
        "parameter_tuning_allowed":False,
        "protected_historical_validation_reuse_for_tuning":False,
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main()->None:
    cert_root=Path("evidence/api_football/market_expansion/player_shots_role_certification")
    ptr=_load(cert_root/"last_run.json")
    model=_load(Path("evidence/api_football/market_expansion/player_shots_expected_minutes_v2/model.json"))
    out=Path("evidence/api_football/player_shots_prospective")
    out.mkdir(parents=True,exist_ok=True)
    ledger=out/"freeze_ledger.jsonl"
    calibration=out/"calibration_ledger.jsonl"
    if not ledger.exists():
        ledger.write_text("",encoding="utf-8")
    if not calibration.exists():
        calibration.write_text("",encoding="utf-8")
    state=build_state(ptr,model)
    (out/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":state["status"],
        "prospective_freeze_allowed":state["prospective_freeze_allowed"],
        "freeze_observation_count":0,
        "gate_30":state["gates"]["30"]["status"],
        "real_money":"BLOCKED"
    },sort_keys=True))

if __name__=="__main__":
    main()
