from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from math import log
from pathlib import Path
from typing import Any, Mapping

EPS=1e-15
THRESHOLDS=(30,50,100)


def _canonical(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def _sha(value:Any)->str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _record_sha(row:Mapping[str,Any])->str:
    body=dict(row); body.pop("record_sha256",None)
    return _sha(body)


def _load_json(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    rows=[]
    for line_number,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),start=1):
        if not raw.strip():
            continue
        try:
            value=json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"INVALID_JSONL:{path}:{line_number}") from exc
        if not isinstance(value,dict):
            raise ValueError(f"JSONL_ROW_NOT_OBJECT:{path}:{line_number}")
        rows.append(value)
    return rows


def audit_calibration_ledger(rows:list[dict[str,Any]])->None:
    previous=None
    seen=set()
    for row in rows:
        fid=str(row.get("fixture_id") or "")
        if not fid or fid in seen:
            raise ValueError("CALIBRATION_LEDGER_DUPLICATE_OR_MISSING_FIXTURE")
        if row.get("previous_record_sha256")!=previous:
            raise ValueError("CALIBRATION_LEDGER_HASH_CHAIN_BROKEN")
        if row.get("record_sha256")!=_record_sha(row):
            raise ValueError("CALIBRATION_LEDGER_RECORD_SHA_MISMATCH")
        if row.get("source_terminal_status")!="FT":
            raise ValueError("CALIBRATION_LEDGER_REQUIRES_FT")
        if row.get("p_matrix_status")!="NOT_GENERATED":
            raise ValueError("CALIBRATION_LEDGER_P_MATRIX_MUST_NOT_EXIST")
        if row.get("real_money")!="BLOCKED":
            raise ValueError("CALIBRATION_LEDGER_REAL_MONEY_MUST_BE_BLOCKED")
        previous=row["record_sha256"]
        seen.add(fid)


def _append_calibration(path:Path,payload:Mapping[str,Any])->dict[str,Any]:
    rows=_load_jsonl(path)
    audit_calibration_ledger(rows)
    fid=str(payload.get("fixture_id") or "")
    if any(str(r["fixture_id"])==fid for r in rows):
        raise ValueError("DUPLICATE_CALIBRATION_OBSERVATION")
    row=dict(payload)
    row["previous_record_sha256"]=rows[-1]["record_sha256"] if rows else None
    row["record_sha256"]=_record_sha(row)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as handle:
        handle.write(_canonical(row)+"\n")
    audit_calibration_ledger(_load_jsonl(path))
    return row


def sync_calibration_ledger(root:Path)->dict[str,Any]:
    freeze=_load_json(root/"prospective_market_freeze/freeze.json")
    settlement_path=root/"prospective_market_freeze/settlement_ledger.jsonl"
    settlements=_load_jsonl(settlement_path)
    calibration_path=root/"prospective_calibration/ledger.jsonl"
    existing=_load_jsonl(calibration_path)
    audit_calibration_ledger(existing)
    existing_ids={str(r["fixture_id"]) for r in existing}

    freeze_by_id={
        str(r["fixture_id"]):r
        for r in freeze.get("rows",[])
        if isinstance(r,Mapping)
    }
    appended=[]
    for settlement in settlements:
        fid=str(settlement.get("fixture_id") or "")
        if fid in existing_ids:
            continue
        if settlement.get("terminal_status")!="FT":
            raise ValueError("NON_FT_SETTLEMENT_CANNOT_ENTER_CALIBRATION")
        freeze_row=freeze_by_id.get(fid)
        if freeze_row is None:
            raise ValueError(f"FREEZE_ROW_MISSING_FOR_SETTLEMENT:{fid}")
        if settlement.get("freeze_at_utc")!=freeze_row.get("freeze_at_utc"):
            raise ValueError(f"FREEZE_TIMESTAMP_MISMATCH:{fid}")
        if settlement.get("input_sha256")!=freeze_row.get("input_sha256"):
            raise ValueError(f"FREEZE_INPUT_SHA_MISMATCH:{fid}")
        if settlement.get("frozen_research_probabilities")!=freeze_row.get("frozen_research_probabilities"):
            raise ValueError(f"FROZEN_PROBABILITY_MISMATCH:{fid}")

        payload={
            "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CALIBRATION_OBSERVATION_V1",
            "fixture_id":fid,
            "target_key":freeze_row["target_key"],
            "kickoff_utc":freeze_row["kickoff_utc"],
            "freeze_at_utc":freeze_row["freeze_at_utc"],
            "settled_at_utc":settlement["settled_at_utc"],
            "input_sha256":freeze_row["input_sha256"],
            "frozen_challenger_probabilities":freeze_row["frozen_research_probabilities"],
            "frozen_poisson_reference":freeze_row["poisson_reference"],
            "outcomes":settlement["outcomes"],
            "source_terminal_status":"FT",
            "source_settlement_record_sha256":settlement["record_sha256"],
            "used_for_parameter_tuning":False,
            "parameters_mutated_after_freeze":False,
            "p_matrix_status":"NOT_GENERATED",
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
        _append_calibration(calibration_path,payload)
        appended.append(fid)
        existing_ids.add(fid)

    rows=_load_jsonl(calibration_path)
    audit_calibration_ledger(rows)
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CALIBRATION_SYNC_V1",
        "synced_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "new_observation_count":len(appended),
        "new_fixture_ids":appended,
        "calibration_observation_count":len(rows),
        "settlement_record_count":len(settlements),
        "ledger_hash_chain_verified":True,
        "parameters_mutated":False,
        "metrics_policy":"SEALED_UNTIL_EACH_THRESHOLD_30_50_100",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _multiclass_metrics(rows:list[dict[str,Any]], source_key:str)->dict[str,float]:
    brier=0.0
    log_loss=0.0
    correct=0
    for row in rows:
        probs=row[source_key]["1x2"]
        actual=row["outcomes"]["1x2"]
        for klass in ("H","D","A"):
            y=1.0 if actual==klass else 0.0
            brier+=(float(probs[klass])-y)**2
        log_loss+=-log(max(float(probs[actual]),EPS))
        correct+=int(max(("H","D","A"),key=lambda k:float(probs[k]))==actual)
    n=len(rows)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":log_loss/n,"accuracy":correct/n}


def _binary_metrics(rows:list[dict[str,Any]], source_key:str,probability_key:str,outcome_key:str)->dict[str,float]:
    brier=0.0
    log_loss=0.0
    for row in rows:
        p=_clip(float(row[source_key][probability_key]))
        y=1.0 if bool(row["outcomes"][outcome_key]) else 0.0
        brier+=(p-y)**2
        log_loss+=-(y*log(p)+(1-y)*log(1-p))
    n=len(rows)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":log_loss/n}


def _market_result(challenger:dict[str,float],poisson:dict[str,float])->dict[str,Any]:
    db=challenger["brier_score"]-poisson["brier_score"]
    dl=challenger["log_loss"]-poisson["log_loss"]
    return {
        "challenger":challenger,
        "poisson":poisson,
        "delta_brier_challenger_minus_poisson":db,
        "delta_log_loss_challenger_minus_poisson":dl,
        "beats_poisson_brier":db<0,
        "beats_poisson_log_loss":dl<0,
        "gate_passed":db<0 and dl<0,
    }


def compute_metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    if not rows:
        raise ValueError("METRICS_REQUIRE_OBSERVATIONS")
    one=_market_result(
        _multiclass_metrics(rows,"frozen_challenger_probabilities"),
        _multiclass_metrics(rows,"frozen_poisson_reference"),
    )
    over=_market_result(
        _binary_metrics(rows,"frozen_challenger_probabilities","over_2_5","over_2_5"),
        _binary_metrics(rows,"frozen_poisson_reference","over_2_5","over_2_5"),
    )
    btts=_market_result(
        _binary_metrics(rows,"frozen_challenger_probabilities","btts_v2","btts"),
        _binary_metrics(rows,"frozen_poisson_reference","btts","btts"),
    )
    return {
        "1x2":one,
        "over_2_5":over,
        "btts_v2":btts,
        "all_three_markets_pass":one["gate_passed"] and over["gate_passed"] and btts["gate_passed"],
    }


def build_gate_state(rows:list[dict[str,Any]])->dict[str,Any]:
    audit_calibration_ledger(rows)
    n=len(rows)
    gates={}
    for threshold in THRESHOLDS:
        if n<threshold:
            gates[str(threshold)]={
                "threshold":threshold,
                "status":"SEALED",
                "observations_available":n,
                "observations_required":threshold,
                "remaining":threshold-n,
                "metrics_opened":False,
                "metrics":None,
            }
        else:
            prefix=rows[:threshold]
            gates[str(threshold)]={
                "threshold":threshold,
                "status":"OPENED_AT_THRESHOLD",
                "observations_available":n,
                "observations_used":threshold,
                "observations_required":threshold,
                "remaining":0,
                "metrics_opened":True,
                "metrics":compute_metrics(prefix),
                "sample_fixture_ids":[r["fixture_id"] for r in prefix],
                "sample_prefix_sha256":_sha([r["record_sha256"] for r in prefix]),
            }
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CALIBRATION_GATES_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "calibration_observation_count":n,
        "gate_30_role":"INFORMATIVE_CHECKPOINT",
        "gate_50_role":"FIRST_FORMAL_EVALUATION",
        "gate_100_role":"STRONG_PROSPECTIVE_GATE",
        "gates":gates,
        "parameter_tuning_allowed":False,
        "original_357_holdout_reuse_allowed":False,
        "p_matrix_status":"NOT_GENERATED",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    root=Path("evidence/api_football")
    sync=sync_calibration_ledger(root)
    out=root/"prospective_calibration"
    out.mkdir(parents=True,exist_ok=True)
    rows=_load_jsonl(out/"ledger.jsonl")
    gates=build_gate_state(rows)
    (out/"sync_last.json").write_text(json.dumps(sync,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (out/"gates.json").write_text(json.dumps(gates,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "calibration_observation_count":gates["calibration_observation_count"],
        "gate_30_status":gates["gates"]["30"]["status"],
        "gate_50_status":gates["gates"]["50"]["status"],
        "gate_100_status":gates["gates"]["100"]["status"],
        "new_observation_count":sync["new_observation_count"],
        "ledger_hash_chain_verified":sync["ledger_hash_chain_verified"],
        "real_money":gates["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
