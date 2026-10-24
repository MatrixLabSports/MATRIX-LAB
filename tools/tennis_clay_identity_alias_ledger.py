from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA="MATRIX_TENNIS_CLAY_IDENTITY_ONLY_ALIAS_LEDGER_V1"
LANE_ID="ATP_CHALLENGER_MEN_SINGLES_CLAY"


def _load(path: Path) -> dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge_ledger(
    *,
    current: Mapping[str,Any] | None,
    crosswalk: Mapping[str,Any],
    source_sha256: str,
) -> dict[str,Any]:
    if crosswalk.get("real_money")!="BLOCKED":
        raise ValueError("CLAY_ALIAS_CROSSWALK_REAL_MONEY_INVALID")
    if crosswalk.get("join_by_name_only") is not False:
        raise ValueError("CLAY_ALIAS_NAME_ONLY_JOIN_FORBIDDEN")
    if str(crosswalk.get("ranking_cut") or "")!="20260921":
        raise ValueError("CLAY_ALIAS_RANKING_CUT_INVALID")

    existing_rows=[
        dict(x) for x in ((current or {}).get("mappings",[]) or [])
        if isinstance(x,Mapping) and x.get("status")=="PASS"
    ]
    by_provider={
        str(x.get("provider_player_id") or ""):x
        for x in existing_rows
        if str(x.get("provider_player_id") or "")
    }
    passed_ids={
        str(pid)
        for event in crosswalk.get("events",[]) or []
        if isinstance(event,Mapping) and event.get("status")=="PASS"
        for pid in event.get("provider_player_ids",[]) or []
        if str(pid).startswith("rapidapi-tennis:player:")
    }

    added=[]
    for raw in crosswalk.get("mappings",[]) or []:
        if not isinstance(raw,Mapping) or raw.get("status")!="PASS":
            continue
        row=dict(raw)
        pid=str(row.get("provider_player_id") or "")
        cid=str(row.get("canonical_source_id") or "")
        name=str(row.get("canonical_name") or "")
        if pid not in passed_ids:
            continue
        if not pid.startswith("rapidapi-tennis:player:") or not cid or not name:
            raise ValueError("CLAY_ALIAS_MAPPING_INVALID:"+pid)
        old=by_provider.get(pid)
        if old is not None:
            if str(old.get("canonical_source_id") or "")!=cid:
                raise ValueError("CLAY_ALIAS_PROVIDER_COLLISION:"+pid)
            continue
        row["identity_only"]=True
        row["model_admission_forbidden"]=True
        by_provider[pid]=row
        added.append(pid)

    mappings=[by_provider[k] for k in sorted(by_provider)]
    sources=list((current or {}).get("source_crosswalks",[]) or [])
    src={
        "sha256":source_sha256,
        "revision":crosswalk.get("revision"),
        "status":crosswalk.get("status"),
        "passed_events":int(crosswalk.get("passed_events") or 0),
    }
    if src not in sources:
        sources.append(src)

    return {
        "schema":SCHEMA,
        "lane_id":LANE_ID,
        "identity_only":True,
        "model_admission_forbidden":True,
        "ranking_cut":"20260921",
        "events":[
            {
                "event_id":"CLAY-IDENTITY-LEDGER-"+pid.split(":")[-1],
                "provider_player_ids":[pid],
                "status":"PASS",
                "blockers":[],
            }
            for pid in sorted(by_provider)
        ],
        "mappings":mappings,
        "mapping_count":len(mappings),
        "added_provider_player_ids":added,
        "added_count":len(added),
        "source_crosswalks":sources,
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--current")
    p.add_argument("--crosswalk",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    cross_path=Path(a.crosswalk)
    current_path=Path(a.current) if a.current else Path(a.out)
    current=_load(current_path) if current_path.exists() else None
    out=merge_ledger(
        current=current,
        crosswalk=_load(cross_path),
        source_sha256=_sha(cross_path),
    )
    path=Path(a.out); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "mapping_count":out["mapping_count"],
        "added_count":out["added_count"],
        "added_provider_player_ids":out["added_provider_player_ids"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
