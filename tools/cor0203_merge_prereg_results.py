from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def merge_prereg_results(
    rapidapi: Mapping[str,Any],
    api_tennis: Mapping[str,Any],
) -> dict[str,Any]:
    rows=[("rapidapi_tennis",rapidapi),("api_tennis",api_tennis)]
    total=sum(int(x.get("events_registered") or 0) for _,x in rows)
    skipped=[]
    event_ids=[]
    revisions=[]
    for provider,payload in rows:
        for event_id in payload.get("event_ids",[]) or []:
            token=str(event_id)
            if token and token not in event_ids:
                event_ids.append(token)
        if payload.get("revision") is not None:
            revisions.append({
                "provider":provider,
                "revision":payload.get("revision"),
                "path":payload.get("path"),
            })
        for row in payload.get("skipped",[]) or []:
            item=dict(row) if isinstance(row,Mapping) else {"raw":row}
            item["provider"]=provider
            skipped.append(item)

    statuses={provider:str(payload.get("status") or "UNKNOWN") for provider,payload in rows}
    if total>0:
        status="PREREGISTERED"
    elif all(v=="NO_DISCOVERY_INPUT" for v in statuses.values()):
        status="NO_DISCOVERY_INPUT"
    else:
        status="NO_NEW_EVENTS"

    starts=[
        int(payload.get("starting_observation_count"))
        for _,payload in rows
        if payload.get("starting_observation_count") is not None
    ]
    return {
        "schema":"MATRIX_COR0203_DUAL_DISCOVERY_PREREGISTRATION_RESULT_V1",
        "status":status,
        "provider_status":"DUAL_RECONCILED",
        "provider_statuses":statuses,
        "created":total>0,
        "events_registered":total,
        "event_ids":event_ids,
        "revisions":revisions,
        "starting_observation_count":min(starts) if starts else None,
        "skipped":skipped,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--rapidapi",required=True)
    parser.add_argument("--api-tennis",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    out=merge_prereg_results(
        _load(Path(args.rapidapi)),
        _load(Path(args.api_tennis)),
    )
    p=Path(args.out)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "events_registered":out["events_registered"],
        "provider_statuses":out["provider_statuses"],
        "real_money":out["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
