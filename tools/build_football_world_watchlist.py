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
DEFAULT_CALENDAR_ROOT=Path("evidence/calendar_physical")
BOGOTA=ZoneInfo("America/Bogota")


def _load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v


def _parse_sofa_time(raw:str,target_date_bogota:str)->datetime|None:
    m=re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})\s+(\d{1,2}):(\d{2})\s+",raw)
    if not m:
        return None
    day,month,year2,hour,minute=map(int,m.groups())
    year=2000+year2
    parsed=datetime(year,month,day,hour,minute,tzinfo=BOGOTA)
    if parsed.date().isoformat()!=target_date_bogota:
        return None
    return parsed


def _flash_temporal_map(temporal:Mapping[str,Any]|None,target_date_bogota:str)->dict[str,str]:
    if temporal is None:
        return {}
    if temporal.get("schema")!="MATRIX_OPERA_FLASHSCORE_TEMPORAL_CAPTURE_V1":
        raise ValueError("FLASHSCORE_TEMPORAL_SCHEMA_MISMATCH")
    if str(temporal.get("target_date_bogota") or "")!=target_date_bogota:
        raise ValueError("FLASHSCORE_TEMPORAL_TARGET_DATE_MISMATCH")
    policy=temporal.get("policy")
    if not isinstance(policy,Mapping):
        raise ValueError("FLASHSCORE_TEMPORAL_POLICY_MISSING")
    if policy.get("exact_name_match_required") is not True or policy.get("single_time_required") is not True:
        raise ValueError("FLASHSCORE_TEMPORAL_EXACT_SINGLE_POLICY_REQUIRED")
    out:dict[str,str]={}
    conflicts:set[str]=set()
    for row in temporal.get("observations") or []:
        if not isinstance(row,Mapping):
            continue
        name=str(row.get("flashscore_observation") or "").strip()
        times=row.get("displayed_times_bogota")
        if not name or row.get("exact_single_display_time") is not True or not isinstance(times,list) or len(times)!=1:
            continue
        value=str(times[0] or "").strip()
        if not re.match(r"^\d{1,2}:\d{2}$",value):
            continue
        if name in out and out[name]!=value:
            conflicts.add(name)
            continue
        out[name]=value
    for name in conflicts:
        out.pop(name,None)
    return out


def _display_time_dt(target_date_bogota:str,display_time:str)->datetime|None:
    m=re.match(r"^(\d{1,2}):(\d{2})$",display_time)
    if not m:
        return None
    try:
        y,mo,d=map(int,target_date_bogota.split("-"))
        h,mi=map(int,m.groups())
        return datetime(y,mo,d,h,mi,tzinfo=BOGOTA)
    except (ValueError,TypeError):
        return None


def build(recon:Mapping[str,Any],generated_at:datetime|None=None,flashscore_temporal:Mapping[str,Any]|None=None)->dict[str,Any]:
    if recon.get("status")!="PASS_OPEN_RECONCILIATION":
        raise ValueError("RECONCILIATION_NOT_PASS")
    target_date=str(recon.get("target_date_bogota") or "")
    flash_times=_flash_temporal_map(flashscore_temporal,target_date)
    confirmed=[]
    for row in recon.get("confirmed_both") or []:
        if not isinstance(row,Mapping):
            continue
        raw=str(row.get("sofascore") or "")
        start=_parse_sofa_time(raw,str(recon.get("target_date_bogota") or ""))
        flash_name=str(row.get("flashscore") or "")
        flash_time=flash_times.get(flash_name)
        flash_dt=_display_time_dt(target_date,flash_time) if flash_time else None
        postponed=("Aplazado" in raw or "Cancelado" in raw)
        if postponed and flash_dt is not None:
            temporal_crosscheck="POSTPONED_CONFLICT_BLOCKED"
        elif start is not None and flash_dt is not None and start.hour==flash_dt.hour and start.minute==flash_dt.minute:
            temporal_crosscheck="DISPLAY_TIME_AGREES"
        elif start is not None and flash_dt is not None:
            temporal_crosscheck="DISPLAY_TIME_CONFLICT"
        elif flash_dt is not None:
            temporal_crosscheck="FLASHSCORE_ONLY_TIME_AVAILABLE"
        else:
            temporal_crosscheck="NO_FLASHSCORE_TIME"
        confirmed.append({
            "event_identity":row.get("flashscore"),
            "sofascore_observation":raw,
            "flashscore_observation":row.get("flashscore"),
            "source_count":2,
            "identity_score":row.get("identity_score"),
            "kickoff_display_bogota":start.isoformat() if start else None,
            "flashscore_display_time_bogota":flash_dt.isoformat() if flash_dt else None,
            "temporal_crosscheck_status":temporal_crosscheck,
            "status":"CONFIRMED_BOTH_IDENTITY",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"KICKOFF_TIME_NOT_INDEPENDENTLY_CERTIFIED_BY_BOTH_SOURCES",
        })
    sofa_only=[]
    for row in recon.get("sofascore_only") or []:
        raw=str(row.get("sofascore") or "")
        start=_parse_sofa_time(raw,str(recon.get("target_date_bogota") or ""))
        sofa_only.append({
            "sofascore_observation":raw,
            "source_count":1,
            "kickoff_display_bogota":start.isoformat() if start else None,
            "status":"SOFASCORE_ONLY_OPEN_RECONCILIATION",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"SECOND_SOURCE_IDENTITY_CONFIRMATION_REQUIRED",
        })
    flash_only=[]
    for row in (recon.get("flashscore_only") or []):
        if not isinstance(row,Mapping):
            continue
        name=str(row.get("flashscore") or "")
        display_time=flash_times.get(name)
        display_dt=_display_time_dt(target_date,display_time) if display_time else None
        flash_only.append({
            "flashscore_observation":row.get("flashscore"),
            "source_count":1,
            "kickoff_display_bogota":display_dt.isoformat() if display_dt else None,
            "temporal_source":"FLASHSCORE_OPERA_EXACT_SINGLE_DISPLAY_TIME" if display_dt else None,
            "status":"FLASHSCORE_ONLY_OPEN_RECONCILIATION",
            "eligible_for_monitoring":True,
            "eligible_for_freeze":False,
            "freeze_blocker":"SOFASCORE_IDENTITY_OR_API_RECONCILIATION_REQUIRED",
        })
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
            "flashscore_exact_single_display_time":sum(1 for x in flash_only if x.get("kickoff_display_bogota")),
        },
        "confirmed_both":confirmed,
        "sofascore_only":sofa_only,
        "flashscore_only":flash_only,
        "ambiguous":ambiguous,
        "policy":{
            "source_order":["SOFASCORE","FLASHSCORE","APIS"],
            "confirmed_identity_does_not_equal_time_certification":True,
            "no_freeze_from_single_source_time":True,
            "flashscore_temporal_exact_name_required":True,
            "flashscore_temporal_single_time_required":True,
            "postponed_conflict_does_not_certify_time":True,
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
    recon=_load(Path(a.reconciliation))
    temporal_path=DEFAULT_CALENDAR_ROOT/str(recon.get("target_date_bogota") or "")/"flashscore_opera_temporal_capture.json"
    temporal=_load(temporal_path) if temporal_path.exists() else None
    result=build(recon,flashscore_temporal=temporal)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"counts":result["counts"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
