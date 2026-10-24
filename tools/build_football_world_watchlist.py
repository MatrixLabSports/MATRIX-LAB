from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Mapping

DEFAULT_RECON=Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_CALENDAR_RECONCILIATION_LAST.json")
DEFAULT_OUT=Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_WATCHLIST_LAST.json")
BOGOTA=ZoneInfo("America/Bogota")


def _load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v


def _parse_sofa_time(raw:str)->datetime|None:
    m=re.match(r"^25/10/26\s+(\d{1,2}):(\d{2})\s+",raw)
    if not m:
        return None
    return datetime(2026,10,25,int(m.group(1)),int(m.group(2)),tzinfo=BOGOTA)


def build(recon:Mapping[str,Any],generated_at:datetime|None=None)->dict[str,Any]:
    if recon.get("status")!="PASS_OPEN_RECONCILIATION":
        raise ValueError("RECONCILIATION_NOT_PASS")
    confirmed=[]
    for row in recon.get("confirmed_both") or []:
        if not isinstance(row,Mapping):
            continue
        raw=str(row.get("sofascore") or "")
        start=_parse_sofa_time(raw)
        confirmed.append({
            "event_identity":row.get("flashscore"),
            "sofascore_observation":raw,
            "flashscore_observation":row.get("flashscore"),
            "source_count":2,
            "identity_score":row.get("identity_score"),
            "kickoff_display_bogota":start.isoformat() if start else None,
            "status":"CONFIRMED_BOTH_IDENTITY",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"KICKOFF_TIME_NOT_INDEPENDENTLY_CERTIFIED_BY_BOTH_SOURCES",
        })
    sofa_only=[]
    for row in recon.get("sofascore_only") or []:
        raw=str(row.get("sofascore") or "")
        start=_parse_sofa_time(raw)
        sofa_only.append({
            "sofascore_observation":raw,
            "source_count":1,
            "kickoff_display_bogota":start.isoformat() if start else None,
            "status":"SOFASCORE_ONLY_OPEN_RECONCILIATION",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"SECOND_SOURCE_IDENTITY_CONFIRMATION_REQUIRED",
        })
    flash_only=[
        {
            "flashscore_observation":row.get("flashscore"),
            "source_count":1,
            "kickoff_display_bogota":None,
            "status":"FLASHSCORE_ONLY_OPEN_RECONCILIATION",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"SOFASCORE_IDENTITY_OR_API_RECONCILIATION_REQUIRED",
        }
        for row in (recon.get("flashscore_only") or []) if isinstance(row,Mapping)
    ]
    ambiguous=[
        {
            "flashscore_observation":row.get("flashscore"),
            "status":"AMBIGUOUS_IDENTITY",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"AMBIGUOUS_IDENTITY_MUST_BE_RESOLVED",
        }
        for row in (recon.get("ambiguous") or []) if isinstance(row,Mapping)
    ]
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
        "schema":"MATRIX_FOOTBALL_WORLD_WATCHLIST_V1",
        "generated_at_utc":now,
        "target_date_bogota":recon.get("target_date_bogota"),
        "status":"PASS_MONITORING_ONLY",
        "counts":{
            "confirmed_both":len(confirmed),
            "sofascore_only":len(sofa_only),
            "flashscore_only":len(flash_only),
            "ambiguous":len(ambiguous),
            "monitoring_total":len(confirmed)+len(sofa_only)+len(flash_only)+len(ambiguous),
            "freeze_eligible":0,
        },
        "confirmed_both":confirmed,
        "sofascore_only":sofa_only,
        "flashscore_only":flash_only,
        "ambiguous":ambiguous,
        "policy":{
            "source_order":["SOFASCORE","FLASHSCORE","APIS"],
            "confirmed_identity_does_not_equal_time_certification":True,
            "no_freeze_from_single_source_time":True,
            "missing_not_zero":True,
            "no_silent_imputation":True,
            "post_start_backfill_forbidden":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--reconciliation",default=str(DEFAULT_RECON))
    p.add_argument("--out",default=str(DEFAULT_OUT))
    a=p.parse_args()
    result=build(_load(Path(a.reconciliation)))
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"counts":result["counts"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
