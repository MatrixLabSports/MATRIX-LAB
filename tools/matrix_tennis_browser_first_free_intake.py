"""Scheduled, browser-first tennis inventory with no paid API or false holdout.
Reads exact SofaScore/Flashscore observations collected in Opera. Link counts
are NEVER treated as verified matches, starts, court surfaces or model rows.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path("evidence/tennis_calendar_physical")
HARD=Path("evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json")
CLAY=Path("evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/prospective/state.json")
SCHEMA="MATRIX_TENNIS_BROWSER_FIRST_FREE_DAILY_INTAKE_V1"
SOURCES=(("SOFASCORE","sofascore_opera_full_link_observations.json","sofascore.com","/tennis/match/"),
         ("FLASHSCORE","flashscore_opera_full_link_observations.json","flashscore.co","/partido/tenis/"))

def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()

def get(root:Path,path:Path):
    p=root/path
    if not p.is_file():return None,None
    raw=p.read_bytes()
    if len(raw)>5_000_000:raise ValueError("SOURCE_FILE_TOO_LARGE")
    return json.loads(raw),sha(raw)

def inventory(root:Path,day:str)->dict:
    date.fromisoformat(day)
    reports=[];all_ok=True
    for source,filename,domain,segment in SOURCES:
        path=ROOT/day/filename
        raw,h=get(root,path)
        if raw is None:
            reports.append({"source":source,"status":"MISSING_CAPTURE","links":0})
            all_ok=False
            continue
        if (raw.get("schema")!="MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1" or
            raw.get("target_date_bogota")!=day or raw.get("source")!=source or
            raw.get("real_money")!="BLOCKED" or
            raw.get("canonical_fixture_export_authorized") is not False or
            raw.get("probability_generation_authorized") is not False or
            raw.get("telegram_signals_authorized") is not False):
            raise ValueError("UNTRUSTED_CALENDAR_CAPTURE_"+source)
        events=raw.get("matches")
        if not isinstance(events,list) or len(events)>3000:
            raise ValueError("INVALID_SOURCE_MATCH_LIST_"+source)
        urls=set();duplicates=0;unknown=0
        for m in events:
            if not isinstance(m,dict):raise ValueError("INVALID_MATCH_RECORD")
            u=m.get("url")
            if not isinstance(u,str):raise ValueError("INVALID_MATCH_URL")
            z=urlparse(u)
            if (z.scheme!="https" or z.hostname not in (domain,"www."+domain)
                or segment not in z.path or z.username or z.password):
                raise ValueError("UNEXPECTED_SOURCE_LINK")
            if u in urls:duplicates+=1
            urls.add(u)
            if not m.get("display_name"):unknown+=1
        if len(urls)!=raw.get("observed_link_count"):
            raise ValueError("CAPTURE_DECLARED_COUNT_CONFLICT_"+source)
        reports.append({"source":source,"status":"AUTHENTIC_LINK_CAPTURE_NOT_FIXTURE_CERTIFICATION",
            "source_file":path.as_posix(),"source_sha256":h,
            "links":len(urls),"duplicate_links":duplicates,
            "missing_visible_names":unknown,
            "individual_match_date_verified":False,
            "surface_per_event_verified":False,
            "cross_provider_identity_verified":False})
    hard,_=get(root,HARD)
    clay,_=get(root,CLAY)
    if hard is None or clay is None:raise ValueError("PROTECTED_MODEL_STATE_MISSING")
    if (hard.get("metrics_opened") is not False or
        clay.get("metrics_opened") is not False or
        int(clay.get("outcomes_read") or 0)!=0 or
        clay.get("real_money")!="BLOCKED"):
        raise ValueError("PROTECTED_HOLDOUT_STATE_INVALID")
    return {"schema":SCHEMA,"target_date_bogota":day,
       "status":"FREE_BROWSER_LINKS_CAPTURED_METADATA_NOT_YET_CERTIFIED" if all_ok
          else "AWAITING_AUTHENTIC_BROWSER_CAPTURE",
       "source_order":["SOFASCORE","FLASHSCORE","SECONDARY_FREE_PROVIDERS"],
       "source_observations":reports,
       "hard_original_unique_observations":hard["unique_calibration_observations"],
       "clay_original_prospective_observations":clay["observation_count"],
       "hard_new_holdout_admissions":0,"clay_new_holdout_admissions":0,
       "holdout_admission_reason":"PER_EVENT_SURFACE_TIME_IDENTITY_AND_PIT_REQUIRED",
       "provider_crosswalk_certified":False,"new_model_parameters":False,
       "paid_api_used":False,"paid_api_required":False,
       "canonical_fixture_export_authorized":False,
       "production_predictions_authorized":False,
       "telegram_signal_authorized":False,"automatic_wagering":False,
       "real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    report=inventory(a.root,a.date)
    out=a.out or Path(f"evidence/tennis_calendar_reconciliation/{a.date}/MATRIX_TENNIS_FREE_BROWSER_FIRST_INTAKE_LAST.json")
    if any(x in out.parts for x in ("holdout","telegram","governance","prospective")):
        raise SystemExit("NO_WRITE_TO_MODEL_OR_TELEGRAM")
    target=out if out.is_absolute() else a.root/out
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],
        "source_links":{x["source"]:x["links"] for x in report["source_observations"]},
        "hard_new_holdout_admissions":0,"clay_new_holdout_admissions":0,
        "real_money":"BLOCKED"},sort_keys=True))
if __name__=="__main__":main()
