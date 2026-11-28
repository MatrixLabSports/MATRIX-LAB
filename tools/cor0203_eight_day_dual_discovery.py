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
    fetch_discovery as rapid_fetch_discovery,
)
from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
    fetch_discovery as api_fetch_discovery,
)

BASE_WINDOW_DAYS=4
EXTENSION_WINDOW_DAYS=4
LOGICAL_HORIZON_DAYS=8


def _load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("DISCOVERY_PAYLOAD_NOT_OBJECT")
    return value


def _event_id(row: Mapping[str,Any]) -> str:
    return str(
        row.get("canonical_source_event_id")
        or row.get("event_id")
        or row.get("source_event_id")
        or ""
    ).strip()


def merge_discovery_payloads(
    base: Mapping[str,Any],
    extension: Mapping[str,Any],
    *,
    provider: str,
    as_of_utc: str,
) -> dict[str,Any]:
    if base.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError(f"{provider.upper()}_BASE_DISCOVERY_NOT_READY")
    if extension.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError(f"{provider.upper()}_EXTENSION_DISCOVERY_NOT_READY")

    merged: dict[str,dict[str,Any]]={}
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
        for row in payload.get("provider_rejected",[]) or []:
            if isinstance(row,Mapping):
                rejected.append(json.loads(json.dumps(row)))

    out=json.loads(json.dumps(base))
    out["schema"]=str(base.get("schema") or "")+"_EIGHT_DAY_MERGED"
    out["provider"]=provider
    out["as_of_utc"]=as_of_utc
    out["status"]="DISCOVERY_COMPLETED"
    out["eligible_candidates"]=[merged[k] for k in sorted(merged)]
    out["eligible_input_events"]=len(merged)
    out["provider_rejected"]=rejected
    out["network_calls"]=int(base.get("network_calls",0) or 0)+int(extension.get("network_calls",0) or 0)
    out["request_count"]=int(base.get("request_count",0) or 0)+int(extension.get("request_count",0) or 0)
    out["eight_day_horizon"]={
        "logical_days":LOGICAL_HORIZON_DAYS,
        "provider_call_max_days":4,
        "base_window_days":BASE_WINDOW_DAYS,
        "extension_window_days":EXTENSION_WINDOW_DAYS,
        "deduplicated_candidate_count":len(merged),
        "duplicate_source_event_ids":sorted(set(duplicate_ids)),
        "duplicate_source_event_count":len(set(duplicate_ids)),
    }
    out["automatic_model_promotion"]=False
    out["automatic_wagering"]=False
    out["real_money"]="BLOCKED"
    return out


def fetch_api_tennis_extension(
    *,
    client: ApiTennisDiscoveryClient,
    start,
    stop,
    as_of_utc: str,
) -> dict[str,Any]:
    """Fetch the +4..+7 block while treating only explicit empty provider results as zero inventory."""
    fixture_probe=client.fixtures(start,stop)
    raw_result=fixture_probe.get("result")
    if isinstance(raw_result,list):
        payload=api_fetch_discovery(
            client=client,
            start=start,
            stop=stop,
            as_of_utc=as_of_utc,
        )
        payload["status"]="DISCOVERY_COMPLETED"
        payload["extension_fixture_probe_nonempty"]=True
        return payload
    if raw_result in (None,False,"") or (isinstance(raw_result,Mapping) and not raw_result):
        return {
            "schema":"MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
            "provider":"api_tennis",
            "as_of_utc":as_of_utc,
            "status":"DISCOVERY_COMPLETED",
            "fixture_rows":0,
            "eligible_input_events":0,
            "eligible_candidates":[],
            "provider_rejected":[],
            "world_registry":{
                "schema":"matrix.world-calendar-registry/1",
                "as_of_utc":as_of_utc,
                "rows":[],
                "world_calendar_input_rows":0,
                "world_calendar_unique_events":0,
                "cor0203_eligible_events":0,
                "cor0203_eligible_event_ids":[],
            },
            "extension_fixture_probe_nonempty":False,
            "extension_empty_result_shape":type(raw_result).__name__,
            "automatic_model_promotion":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    raise ApiTennisDiscoveryError(
        "API_TENNIS_EXTENSION_UNEXPECTED_RESULT_TYPE:"+type(raw_result).__name__
    )


def run(
    *,
    rapid_current_path: Path,
    api_current_path: Path,
    rapid_out_path: Path,
    api_out_path: Path,
    audit_out_path: Path,
    as_of_utc: str,
) -> dict[str,Any]:
    now=datetime.fromisoformat(as_of_utc.replace("Z","+00:00")).astimezone(timezone.utc)
    base_start=now.date()
    extension_start=base_start+timedelta(days=BASE_WINDOW_DAYS)
    extension_stop=extension_start+timedelta(days=EXTENSION_WINDOW_DAYS-1)

    rapid_key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    api_key=os.environ.get("API_TENNIS_KEY","").strip()
    if not rapid_key or not api_key:
        raise ValueError("TWO_PAID_TENNIS_KEYS_REQUIRED")

    # Each physical provider request remains bounded to four calendar days.
    rapid_client=RapidApiTennisClient(rapid_key)
    rapid_ext=rapid_fetch_discovery(
        client=rapid_client,
        start=extension_start,
        stop=extension_stop,
        as_of_utc=now.isoformat(),
    )
    rapid_ext["status"]="DISCOVERY_COMPLETED"
    rapid_ext["network_calls"]=rapid_client.request_count

    api_client=ApiTennisDiscoveryClient(api_key)
    api_ext=fetch_api_tennis_extension(
        client=api_client,
        start=extension_start,
        stop=extension_stop,
        as_of_utc=now.isoformat(),
    )
    api_ext["network_calls"]=api_client.request_count
    api_ext["request_count"]=api_client.request_count

    rapid_base=_load(rapid_current_path)
    api_base=_load(api_current_path)
    rapid_merged=merge_discovery_payloads(
        rapid_base,rapid_ext,provider="rapidapi_tennis",as_of_utc=now.isoformat()
    )
    api_merged=merge_discovery_payloads(
        api_base,api_ext,provider="api_tennis",as_of_utc=now.isoformat()
    )

    rapid_out_path.write_text(json.dumps(rapid_merged,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    api_out_path.write_text(json.dumps(api_merged,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")

    audit={
        "schema":"MATRIX_COR0203_DUAL_EIGHT_DAY_HORIZON_V1",
        "as_of_utc":now.isoformat(),
        "base_window":{
            "start":base_start.isoformat(),
            "stop":(base_start+timedelta(days=BASE_WINDOW_DAYS-1)).isoformat(),
            "days":BASE_WINDOW_DAYS,
        },
        "extension_window":{
            "start":extension_start.isoformat(),
            "stop":extension_stop.isoformat(),
            "days":EXTENSION_WINDOW_DAYS,
        },
        "logical_horizon_days":LOGICAL_HORIZON_DAYS,
        "provider_call_max_days":4,
        "rapidapi_tennis":{
            "base_candidates":len(rapid_base.get("eligible_candidates",[]) or []),
            "extension_candidates":len(rapid_ext.get("eligible_candidates",[]) or []),
            "merged_candidates":len(rapid_merged.get("eligible_candidates",[]) or []),
            "extension_network_calls":rapid_client.request_count,
        },
        "api_tennis":{
            "base_candidates":len(api_base.get("eligible_candidates",[]) or []),
            "extension_candidates":len(api_ext.get("eligible_candidates",[]) or []),
            "merged_candidates":len(api_merged.get("eligible_candidates",[]) or []),
            "extension_network_calls":api_client.request_count,
        },
        "dedupe_before_dual_reconciliation":True,
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


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--rapid-current",required=True)
    p.add_argument("--api-current",required=True)
    p.add_argument("--rapid-out",required=True)
    p.add_argument("--api-out",required=True)
    p.add_argument("--audit-out",required=True)
    p.add_argument("--as-of-utc")
    args=p.parse_args()
    as_of=args.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        audit=run(
            rapid_current_path=Path(args.rapid_current),
            api_current_path=Path(args.api_current),
            rapid_out_path=Path(args.rapid_out),
            api_out_path=Path(args.api_out),
            audit_out_path=Path(args.audit_out),
            as_of_utc=as_of,
        )
    except (RapidApiTennisDiscoveryError,ApiTennisDiscoveryError) as exc:
        raise SystemExit("EIGHT_DAY_DISCOVERY_PROVIDER_ERROR:"+type(exc).__name__+":"+str(exc)[:400])
    print(json.dumps({
        "status":audit["status"],
        "logical_horizon_days":audit["logical_horizon_days"],
        "rapidapi_extension_candidates":audit["rapidapi_tennis"]["extension_candidates"],
        "api_tennis_extension_candidates":audit["api_tennis"]["extension_candidates"],
        "real_money":audit["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
