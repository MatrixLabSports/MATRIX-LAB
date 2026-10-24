from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

FINAL_STATUSES={"FT","AET","PEN"}


def _load(p:Path)->dict[str,Any]:
    d=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d,dict): raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return d


def _utc(v:Any)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None: raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return d.astimezone(timezone.utc)


def settle(root:Path)->dict[str,Any]:
    freeze_path=root/"evidence/api_football/prospective_market_freeze/freeze.json"
    freeze=_load(freeze_path)
    rows=freeze.get("rows")
    if not isinstance(rows,list): raise ValueError("FREEZE_ROWS_MISSING")

    settled=0; pending=0
    out_rows=[]
    for row in rows:
        item=dict(row)
        if item.get("settlement_status")=="FINAL":
            out_rows.append(item); settled+=1; continue
        raw_path=root/str(item["historical_baseline_source"])
        payload=_load(raw_path) if raw_path.exists() else {}
        found=None
        for candidate in payload.get("response",[]) if isinstance(payload.get("response"),list) else []:
            if not isinstance(candidate,Mapping): continue
            fixture=candidate.get("fixture"); goals=candidate.get("goals")
            if not isinstance(fixture,Mapping) or str(fixture.get("id"))!=str(item["fixture_id"]): continue
            status=fixture.get("status")
            if not isinstance(status,Mapping) or str(status.get("short") or "").upper() not in FINAL_STATUSES:
                continue
            if not isinstance(goals,Mapping): continue
            hg,ag=goals.get("home"),goals.get("away")
            if not isinstance(hg,int) or not isinstance(ag,int): continue
            found=(hg,ag)
            break
        if found is None:
            pending+=1
            out_rows.append(item)
            continue
        hg,ag=found
        item["outcome"]={
            "home_goals":hg,
            "away_goals":ag,
            "1x2":"H" if hg>ag else "D" if hg==ag else "A",
            "over_2_5":hg+ag>=3,
            "btts":hg>0 and ag>0,
        }
        item["settlement_status"]="FINAL"
        item["settled_at_utc"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        settled+=1
        out_rows.append(item)

    result=dict(freeze)
    result["rows"]=out_rows
    result["settlement_summary"]={
        "final_count":settled,
        "pending_final_count":pending,
        "settlement_final_only":True,
        "nonfinal_outcomes_read":False,
    }
    return result


def main()->None:
    root=Path(".")
    data=settle(root)
    out=root/"evidence/api_football/prospective_market_freeze/settlement.json"
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(data["settlement_summary"],sort_keys=True))


if __name__=="__main__":
    main()
