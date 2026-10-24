from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY=Path("evidence/governance/MATRIX_CANONICAL_SOURCE_REGISTRY.json")
DEFAULT_OUT=Path("evidence/governance/MATRIX_CANONICAL_TRUTH_GUARD_LAST.json")


def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return value


def get_path(value:Any,path:str)->Any:
    cur=value
    for token in path.split("."):
        if not isinstance(cur,dict) or token not in cur:
            raise KeyError(path)
        cur=cur[token]
    return cur


def parse_dt(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def evaluate_source(name:str,spec:dict[str,Any],now:datetime)->dict[str,Any]:
    path=Path(str(spec["canonical_path"]))
    result={"name":name,"canonical_path":str(path),"status":"PASS","failures":[]}
    if not path.exists():
        result["status"]="FAIL_CLOSED"
        result["failures"].append("CANONICAL_SOURCE_MISSING")
        return result

    payload=load(path)
    schema=payload.get("schema")
    required_schema=spec.get("required_schema")
    if required_schema and schema!=required_schema:
        result["failures"].append(f"SCHEMA_MISMATCH:{schema}!={required_schema}")

    timestamp_field=str(spec.get("timestamp_field") or "generated_at_utc")
    try:
        ts=parse_dt(get_path(payload,timestamp_field))
        age=max(0.0,(now-ts).total_seconds()/60.0)
        result["source_timestamp_utc"]=ts.isoformat()
        result["age_minutes"]=round(age,2)
        max_age=float(spec["max_age_minutes"])
        result["max_age_minutes"]=max_age
        if age>max_age:
            result["failures"].append("CANONICAL_SOURCE_STALE")
    except Exception as exc:
        result["failures"].append(f"TIMESTAMP_INVALID:{type(exc).__name__}")

    metric_paths=[]
    if "metric_path" in spec:
        metric_paths.append(str(spec["metric_path"]))
    metric_paths.extend(str(x) for x in spec.get("metric_paths",[]) or [])
    metrics={}
    for mp in metric_paths:
        try:
            metrics[mp]=get_path(payload,mp)
        except Exception:
            result["failures"].append(f"METRIC_PATH_MISSING:{mp}")
    result["metrics"]=metrics

    if name=="football_4000":
        try:
            g=payload["global"]
            if int(g["valid_final_settlement_count"])+int(g["pending_count"])+int(g["blocked_count"])!=int(g["frozen_event_count"]):
                result["failures"].append("FOOTBALL_GLOBAL_RECONCILIATION_FAILED")
            if int(g["valid_final_settlement_count"])!=int(g["calibration_observation_count"]):
                result["failures"].append("FOOTBALL_CALIBRATION_COUNTER_MISMATCH")
            if payload.get("counter_precedence",{}).get("target_4000")!="global.valid_final_settlement_count":
                result["failures"].append("FOOTBALL_COUNTER_PRECEDENCE_INVALID")
        except Exception as exc:
            result["failures"].append(f"FOOTBALL_RECONCILIATION_ERROR:{type(exc).__name__}")

    if result["failures"]:
        result["status"]="FAIL_CLOSED"
    return result


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--registry",default=str(DEFAULT_REGISTRY))
    p.add_argument("--out",default=str(DEFAULT_OUT))
    args=p.parse_args()

    registry=load(Path(args.registry))
    now=datetime.now(timezone.utc)
    checks={}
    failures=[]
    for name,spec in (registry.get("sources") or {}).items():
        r=evaluate_source(str(name),dict(spec),now)
        checks[name]=r
        if r["status"]!="PASS":
            failures.append({"source":name,"failures":r["failures"]})

    report={
        "schema":"MATRIX_CANONICAL_TRUTH_GUARD_V1",
        "generated_at_utc":now.isoformat(),
        "precedence":registry.get("precedence"),
        "response_contract":registry.get("response_contract"),
        "checks":checks,
        "summary":{
            "status":"PASS" if not failures else "FAIL_CLOSED",
            "registered_sources":len(checks),
            "failed_sources":len(failures),
        },
        "failures":failures,
        "real_money":"BLOCKED",
    }
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report["summary"],sort_keys=True))
    if failures:
        raise SystemExit(2)


if __name__=="__main__":
    main()
