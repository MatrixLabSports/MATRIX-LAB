from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import (
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
    fetch_discovery,
)

BASE_WINDOW_DAYS=4
EXTENSION_WINDOW_DAYS=4
LOGICAL_HORIZON_DAYS=8


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("DISCOVERY_PAYLOAD_NOT_OBJECT")
    return value


def _event_id(row:Mapping[str,Any])->str:
    return str(row.get("canonical_source_event_id") or row.get("event_id") or row.get("source_event_id") or "").strip()


def merge(base:Mapping[str,Any],extension:Mapping[str,Any],*,as_of_utc:str)->dict[str,Any]:
    if base.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("RAPIDAPI_BASE_DISCOVERY_NOT_READY")
    if extension.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("RAPIDAPI_EXTENSION_DISCOVERY_NOT_READY")
    merged={}
    duplicate_ids=[]
    for payload in (base,extension):
        for raw in payload.get("eligible_candidates",[]) or []:
            if not isinstance(raw,Mapping):
                continue
            eid=_event_id(raw)
            if not eid:
                raise ValueError("CANDIDATE_EVENT_ID_MISSING")
            if eid in merged:
                duplicate_ids.append(eid)
                continue
            merged[eid]=json.loads(json.dumps(raw))
    rejected=[]
    for payload in (base,extension):
        rejected.extend(
            json.loads(json.dumps(row))
            for row in (payload.get("provider_rejected",[]) or [])
            if isinstance(row,Mapping)
        )
    out=json.loads(json.dumps(base))
    out["schema"]=str(base.get("schema") or "")+"_EIGHT_DAY_RAPIDAPI"
    out["provider"]="rapidapi_tennis"
    out["as_of_utc"]=as_of_utc
    out["status"]="DISCOVERY_COMPLETED"
    out["eligible_candidates"]=[merged[k] for k in sorted(merged)]
    out["eligible_input_events"]=len(merged)
    out["provider_rejected"]=rejected
    out["network_calls"]=int(base.get("network_calls",0) or 0)+int(extension.get("network_calls",0) or 0)
    out["request_count"]=int(base.get("request_count",0) or 0)+int(extension.get("request_count",0) or 0)
    out["eight_day_horizon"]={
        "logical_days":8,
        "provider_call_max_days":4,
        "base_window_days":4,
        "extension_window_days":4,
        "deduplicated_candidate_count":len(merged),
        "duplicate_source_event_ids":sorted(set(duplicate_ids)),
        "duplicate_source_event_count":len(set(duplicate_ids)),
    }
    out["source_architecture"]="RAPIDAPI_PRIMARY_WITH_OPEN_CALENDAR_RECONCILIATION"
    out["api_tennis_status"]="RETIRED_COST_UTILITY_DECISION"
    out["automatic_model_promotion"]=False
    out["automatic_wagering"]=False
    out["real_money"]="BLOCKED"
    return out


def run(*,rapid_current_path:Path,rapid_out_path:Path,audit_out_path:Path,as_of_utc:str)->dict[str,Any]:
    now=datetime.fromisoformat(as_of_utc.replace("Z","+00:00")).astimezone(timezone.utc)
    extension_start=now.date()+timedelta(days=BASE_WINDOW_DAYS)
    extension_stop=extension_start+timedelta(days=EXTENSION_WINDOW_DAYS-1)
    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise ValueError("RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED")
    client=RapidApiTennisClient(key)
    ext=fetch_discovery(client=client,start=extension_start,stop=extension_stop,as_of_utc=now.isoformat())
    ext["status"]="DISCOVERY_COMPLETED"
    ext["network_calls"]=client.request_count
    base=_load(rapid_current_path)
    merged=merge(base,ext,as_of_utc=now.isoformat())
    rapid_out_path.write_text(json.dumps(merged,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    audit={
        "schema":"MATRIX_COR0203_RAPIDAPI_EIGHT_DAY_HORIZON_V2",
        "as_of_utc":now.isoformat(),
        "logical_horizon_days":8,
        "provider_call_max_days":4,
        "rapidapi_tennis":{
            "base_candidates":len(base.get("eligible_candidates",[]) or []),
            "extension_candidates":len(ext.get("eligible_candidates",[]) or []),
            "merged_candidates":len(merged.get("eligible_candidates",[]) or []),
            "extension_network_calls":client.request_count,
        },
        "required_paid_providers":["rapidapi_tennis"],
        "retired_paid_sources":{"api_tennis":"RETIRED_COST_UTILITY_DECISION"},
        "required_open_calendar_reconciliation":["SofaScore","Flashscore"],
        "metrics_opened":False,
        "outcomes_read":0,
        "odds_to_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    audit_out_path.parent.mkdir(parents=True,exist_ok=True)
    audit_out_path.write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--rapid-current",required=True)
    p.add_argument("--rapid-out",required=True)
    p.add_argument("--audit-out",required=True)
    p.add_argument("--as-of-utc")
    a=p.parse_args()
    as_of=a.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        audit=run(
            rapid_current_path=Path(a.rapid_current),
            rapid_out_path=Path(a.rapid_out),
            audit_out_path=Path(a.audit_out),
            as_of_utc=as_of,
        )
    except RapidApiTennisDiscoveryError as exc:
        raise SystemExit("RAPIDAPI_EIGHT_DAY_PROVIDER_ERROR:"+str(exc)[:400])
    print(json.dumps({
        "status":audit["status"],
        "logical_horizon_days":audit["logical_horizon_days"],
        "rapidapi_extension_candidates":audit["rapidapi_tennis"]["extension_candidates"],
        "api_tennis_status":"RETIRED_COST_UTILITY_DECISION",
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
