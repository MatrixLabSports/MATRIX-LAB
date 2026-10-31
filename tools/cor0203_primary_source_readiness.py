from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _canonical(v:Mapping[str,Any])->bytes:
    return (json.dumps(dict(v),sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()


def classify(*,rapidapi:Mapping[str,Any],horizon:Mapping[str,Any])->dict[str,Any]:
    provider=str(rapidapi.get("provider") or "UNKNOWN")
    status=str(rapidapi.get("status") or "UNKNOWN")
    calls=int(rapidapi.get("network_calls") or 0)
    provider_ready=(
        provider=="rapidapi_tennis"
        and status=="DISCOVERY_COMPLETED"
        and calls>0
        and str(rapidapi.get("real_money") or "BLOCKED")=="BLOCKED"
        and not bool(rapidapi.get("automatic_wagering"))
    )
    horizon_ok=(
        str(horizon.get("status") or "")=="PASS"
        and int(horizon.get("logical_horizon_days") or 0)>=8
        and str(horizon.get("real_money") or "BLOCKED")=="BLOCKED"
    )
    ready=provider_ready and horizon_ok
    if not provider_ready:
        cause="RAPIDAPI_PRIMARY_NOT_READY"
    elif not horizon_ok:
        cause="RAPIDAPI_EIGHT_DAY_HORIZON_NOT_READY"
    else:
        cause="READY"
    identity={
        "provider":"rapidapi_tennis_primary_with_open_reconciliation",
        "status":"PRIMARY_PAID_DISCOVERY_COMPLETED" if ready else "PRIMARY_PAID_DISCOVERY_BLOCKED",
        "ready":ready,
        "cause":cause,
        "required_paid_providers":["rapidapi_tennis"],
        "retired_paid_sources":{
            "api_tennis":{
                "status":"RETIRED_COST_UTILITY_DECISION",
                "subscription":"EXPIRED_NOT_RENEWED",
                "required":False,
            }
        },
        "required_open_calendar_reconciliation":["SofaScore","Flashscore"],
        "open_source_role":"CALENDAR_DISCOVERY_AND_RECONCILIATION",
        "provider_state":{
            "provider":provider,
            "status":status,
            "network_calls":calls,
            "ready":provider_ready,
        },
        "horizon":{
            "status":str(horizon.get("status") or "UNKNOWN"),
            "logical_horizon_days":int(horizon.get("logical_horizon_days") or 0),
        },
    }
    fingerprint=hashlib.sha256(_canonical(identity)).hexdigest()
    return {
        "schema":"MATRIX_COR0203_PRIMARY_SOURCE_READINESS_V2",
        **identity,
        "network_calls":calls,
        "status_fingerprint":fingerprint,
        "production_discovery_ready":ready,
        "two_paid_sources_required":False,
        "provider_policy":"ONE_PAID_PRIMARY_PLUS_REQUIRED_OPEN_CALENDAR_RECONCILIATION",
        "automatic_provider_switch":False,
        "metrics_opened":False,
        "outcomes_read":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def persist_transition(report:Mapping[str,Any],evidence_dir:Path)->tuple[Path,bool]:
    evidence_dir.mkdir(parents=True,exist_ok=True)
    fp=str(report["status_fingerprint"])
    path=evidence_dir/("MATRIX_COR0203_SOURCE_READINESS_PRIMARY_"+fp[:16]+".json")
    if path.exists():
        return path,False
    path.write_text(json.dumps(dict(report),indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return path,True


def _load(path:str)->dict[str,Any]:
    v=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise ValueError("SOURCE_INPUT_NOT_OBJECT:"+path)
    return v


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--rapidapi",required=True)
    p.add_argument("--horizon",required=True)
    p.add_argument("--evidence-dir",default="evidence/cor0203/source_readiness")
    p.add_argument("--summary-out",required=True)
    a=p.parse_args()
    report=classify(rapidapi=_load(a.rapidapi),horizon=_load(a.horizon))
    evidence_path,created=persist_transition(report,Path(a.evidence_dir))
    summary={**report,"evidence_path":str(evidence_path),"evidence_created":created}
    out=Path(a.summary_out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":report["status"],
        "ready":report["ready"],
        "cause":report["cause"],
        "provider_policy":report["provider_policy"],
        "api_tennis_status":"RETIRED_COST_UTILITY_DECISION",
        "real_money":"BLOCKED",
    },sort_keys=True))
    if not report["ready"]:
        raise SystemExit("PRIMARY_SOURCE_NOT_READY:"+str(report["cause"]))


if __name__=="__main__":
    main()
