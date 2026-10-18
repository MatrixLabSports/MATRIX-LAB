from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryClient, ApiTennisDiscoveryError

NONSTANDARD={"RETIRED","WALKOVER","WO","CANCELLED","CANCELED","ABANDONED"}


def _final_pair(value: object) -> tuple[int,int] | None:
    nums=re.findall(r"\d+",str(value or ""))
    if len(nums)<2:
        return None
    a,b=int(nums[0]),int(nums[1])
    if a==b:
        return None
    return a,b


def settle_ledger(*, ledger: dict[str,Any], client: ApiTennisDiscoveryClient, max_requests: int=20) -> dict[str,Any]:
    states=[dict(x) for x in ledger.get("states",[]) or [] if isinstance(x,Mapping)]
    by_match: dict[str,list[dict[str,Any]]]={}
    for row in states:
        mid=str(row.get("match_id") or "").strip()
        if mid:
            by_match.setdefault(mid,[]).append(row)

    reports=[]; requests0=client.request_count
    for mid,rows in sorted(by_match.items()):
        if all(r.get("settlement_status")=="FINAL_STANDARD" for r in rows):
            reports.append({"match_id":mid,"status":"ALREADY_SETTLED"})
            continue
        if client.request_count-requests0>=max_requests:
            reports.append({"match_id":mid,"status":"BLOCKED_REQUEST_BUDGET"})
            continue
        try:
            payload=client.fixture_by_match_key(mid)
        except (ApiTennisDiscoveryError,ValueError) as e:
            reports.append({"match_id":mid,"status":"BLOCKED_PROVIDER","reason":type(e).__name__+":"+str(e)[:200]})
            continue
        result=payload.get("result") if isinstance(payload,Mapping) else None
        exact=[
            x for x in (result or [])
            if isinstance(x,Mapping) and str(x.get("event_key") or "")==mid
        ] if isinstance(result,list) else []
        if len(exact)!=1:
            reports.append({"match_id":mid,"status":"BLOCKED_EXACT_EVENT_REQUIRED","rows":len(exact)})
            continue
        fixture=exact[0]
        status=str(fixture.get("event_status") or "").strip().upper()
        if status in NONSTANDARD:
            reports.append({"match_id":mid,"status":"BLOCKED_NONSTANDARD_TERMINAL","provider_status":status})
            continue
        if status!="FINISHED":
            reports.append({"match_id":mid,"status":"PENDING_FINAL","provider_status":status})
            continue
        pair=_final_pair(fixture.get("event_final_result"))
        if pair is None:
            reports.append({"match_id":mid,"status":"BLOCKED_FINAL_RESULT_INVALID","raw":fixture.get("event_final_result")})
            continue
        label=1 if pair[0]>pair[1] else 0
        for row in rows:
            row["settlement_status"]="FINAL_STANDARD"
            row["label_opened"]=True
            row["p1_match_win"]=label
            row["settlement_provider"]="api_tennis"
            row["settlement_identity"]="EXACT_PROVIDER_EVENT_KEY"
        reports.append({"match_id":mid,"status":"FINAL_STANDARD","p1_match_win":label})

    ordered=sorted(
        [r for rows in by_match.values() for r in rows],
        key=lambda x:(str(x.get("captured_at_utc") or ""),str(x.get("match_id") or ""),str(x.get("state_key") or ""))
    )
    ledger=dict(ledger)
    ledger["states"]=ordered
    ledger["provider_native_settlement"]={
        "schema":"MATRIX_LIVE_TENNIS_API_TENNIS_NATIVE_SETTLEMENT_V1",
        "reports":reports,
        "network_calls":client.request_count-requests0,
        "final_standard_matches":sum(1 for x in reports if x["status"]=="FINAL_STANDARD"),
        "pending_matches":sum(1 for x in reports if x["status"]=="PENDING_FINAL"),
        "blocked_matches":sum(1 for x in reports if x["status"].startswith("BLOCKED_")),
        "cross_provider_equivalence_required":False,
        "same_provider_exact_event_key_required":True,
        "metrics_opened":False,
        "automatic_model_feed":False,
        "real_money":"BLOCKED",
    }
    return ledger


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",required=True)
    p.add_argument("--max-requests",type=int,default=20)
    a=p.parse_args()
    key=os.environ.get("API_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("API_TENNIS_KEY_NOT_CONFIGURED")
    path=Path(a.ledger)
    ledger=json.loads(path.read_text(encoding="utf-8"))
    result=settle_ledger(ledger=ledger,client=ApiTennisDiscoveryClient(key),max_requests=a.max_requests)
    path.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    s=result["provider_native_settlement"]
    print(json.dumps({
        "final_standard_matches":s["final_standard_matches"],
        "pending_matches":s["pending_matches"],
        "blocked_matches":s["blocked_matches"],
        "network_calls":s["network_calls"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
