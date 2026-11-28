"""Fail-closed Challenger research: conflicting authentic before-kickoff captures.

Does not replace previously captured evidence or manufacture a kickoff.
Never opens Hard/Clay calibration or real-money signaling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

CAPTURE = Path("evidence/tennis_calendar_physical")
DETAIL = "sofascore_verified_match_details.json"
ATTEMPT = "MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_LAST.json"
OUT = "MATRIX_TENNIS_CAPTURE_TEMPORAL_DRIFT_GUARD_LAST.json"
SCHEMA = "MATRIX_TENNIS_AUTHENTIC_CAPTURE_TEMPORAL_DRIFT_GUARD_V1"

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def instant(value: object) -> datetime:
    if not isinstance(value,str):
        raise ValueError("CAPTURE_CLOCK_MISSING")
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("CAPTURE_CLOCK_TIMEZONE_MISSING")
    return d.astimezone(timezone.utc)

def _load(path:Path) -> tuple[dict,str]:
    raw=path.read_bytes()
    if len(raw)>8_000_000:
        raise ValueError("CHALLENGER_CAPTURE_SIZE_TOO_LARGE")
    d=json.loads(raw)
    if not isinstance(d,dict):
        raise ValueError("CHALLENGER_CAPTURE_NOT_OBJECT")
    return d,sha(raw)

def identity(row:dict) -> tuple:
    players=row.get("players")
    if not isinstance(players,list) or len(players)!=2:
        raise ValueError("VISIBLE_MATCH_PLAYER_COUNT_NOT_TWO")
    names=[]
    for p in players:
        if not isinstance(p,dict) or not p.get("name") or not p.get("sofascore_player_id"):
            raise ValueError("VISIBLE_MATCH_PLAYER_IDENTITY_INCOMPLETE")
        names.append((
            str(p["sofascore_player_id"]),
            re.sub(r"\s+"," ",str(p["name"]).strip().casefold()),
        ))
    if len(set(x[0] for x in names))!=2:
        raise ValueError("DUPLICATE_VISIBLE_PLAYER_ID")
    return tuple(sorted(names))

def compare(original:dict, attempt:dict, original_sha:str,
            attempt_sha:str, *, now:datetime|None=None)->dict:
    now=(now or datetime.now(timezone.utc))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("DRIFT_GUARD_NOW_UNZONED")
    for item in (original,attempt):
        if (item.get("schema")!="MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
            or item.get("real_money")!="BLOCKED"
            or item.get("new_model_observations_admitted")!=0
            or item.get("telegram_signal_authorized") is not False
            or item.get("capture_method")!="AUTHORIZED_WINDOWS_CDP_SOFASCORE_VISIBLE_MATCH_PAGES"
            or item.get("calendar_backend_api_called") is not False):
            raise ValueError("DRIFT_GUARD_UNTRUSTED_CAPTURE")
    day=original.get("target_date_bogota")
    if day!=attempt.get("target_date_bogota"):
        raise ValueError("DRIFT_GUARD_DIFFERENT_CAPTURE_DATES")
    date.fromisoformat(day)
    original_time=instant(original.get("observed_at_utc"))
    later_time=instant(attempt.get("observed_at_utc"))
    if later_time>now.astimezone(timezone.utc):
        raise ValueError("DRIFT_GUARD_LATER_ATTEMPT_FROM_FUTURE")
    status=attempt.get("status")
    if status=="REJECTED_REGRESSED_DETAILS_PRESERVED":
        if attempt.get("preserved_original_detail_sha256")!=original_sha:
            raise ValueError("DRIFT_GUARD_SAVED_ORIGINAL_SHA_NOT_EQUAL")
    if status not in (
        "REJECTED_REGRESSED_DETAILS_PRESERVED",
        "VERIFIED_VISIBLE_CHALLENGER_METADATA_RESEARCH_ONLY",
        "NO_AUTHENTIC_VISIBLE_CHALLENGER_DETAILS_VERIFIED",
    ):
        raise ValueError("DRIFT_GUARD_UNEXPECTED_CAPTURE_STATUS")
    indexed={}
    for row in attempt.get("events") or []:
        mid=str(row.get("sofascore_event_id") or "")
        if not mid or mid in indexed:
            raise ValueError("DRIFT_GUARD_DUPLICATE_LATER_EVENT")
        indexed[mid]=row
    events=[]
    covered=0
    for row in original.get("events") or []:
        mid=str(row.get("sofascore_event_id") or "")
        after=indexed.get(mid)
        flags=[]
        delta_minutes=None
        if after is None:
            flags.append("NOT_REOBSERVED_IN_LATER_AUTHENTIC_CAPTURE")
        else:
            covered+=1
            if identity(row)!=identity(after):
                flags.append("VISIBLE_PLAYER_IDENTITY_CHANGED_IN_LATER_CAPTURE")
            if (row.get("surface"),row.get("court_label")) != (
                after.get("surface"),after.get("court_label")):
                flags.append("SURFACE_OR_COURT_CHANGED_IN_LATER_CAPTURE")
            first=instant(row.get("kickoff_utc"))
            newest=instant(after.get("kickoff_utc"))
            delta_minutes=int((newest-first).total_seconds()/60)
            if first!=newest:
                flags.append("KICKOFF_CHANGED_IN_LATER_AUTHENTIC_CAPTURE")
        events.append({
            "sofascore_id":mid,"older_kickoff_utc":row.get("kickoff_utc"),
            "later_kickoff_utc":after.get("kickoff_utc") if after else None,
            "kickoff_change_minutes":delta_minutes,
            "observed_again_with_same_identity":(
                after is not None and identity(row)==identity(after)
                if after is not None else False),
            "temporal_quarantined":bool(flags),
            "blocked_reasons":flags,
            "provider_identity_equivalence_certified":False,
            "official_holdout_admitted":False,
        })
    distinct_affected=[x for x in events if x["temporal_quarantined"]]
    return {
        "schema":SCHEMA,"target_date_bogota":day,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"NO_LATER_CAPTURE_AFTER_ORIGINAL" if later_time<=original_time
                 else "QUARANTINE_CHANGED_OR_UNREOBSERVED_EVENT_TIMES"
                    if distinct_affected else "LATER_CAPTURE_RECONSISTENT_RESEARCH_ONLY",
        "original_detail_sha256":original_sha,"later_capture_attempt_sha256":attempt_sha,
        "original_capture_utc":original_time.isoformat(),
        "later_capture_utc":later_time.isoformat(),
        "original_verified_match_count":len(original.get("events") or []),
        "later_verified_match_count":len(attempt.get("events") or []),
        "old_verified_matches_reobserved":covered,
        "old_verified_matches_quarantined":len(distinct_affected),
        "old_verified_kickoff_changed_count":sum(
            "KICKOFF_CHANGED_IN_LATER_AUTHENTIC_CAPTURE" in x["blocked_reasons"] for x in events),
        "later_attempt_exhausted_original_authority_pair_candidates":attempt.get(
            "date_coverage_exhaustive_for_original_authority_pair_candidates"),
        "evidence_origin":"NORMAL_AUTHORIZED_SOFASCORE_MATCH_PAGE_CAPTURE",
        "independently_certified_correct_kickoff_utc":False,
        "source_metadata_quarantine_only":True,
        "new_hard_holdout_admissions":0,
        "new_clay_holdout_admissions":0,
        "telegram_signal_authorized":False,
        "real_money":"BLOCKED",
        "events":events,
    }

def run(root:Path,day:str)->dict:
    date.fromisoformat(day)
    path=root/CAPTURE/day
    old,old_sha=_load(path/DETAIL)
    recent=path/ATTEMPT
    if not recent.is_file():
        return {
            "schema":SCHEMA,"target_date_bogota":day,
            "status":"NO_LATER_CAPTURE_ATTEMPT_NOT_COVERAGE_CERTIFICATION",
            "original_detail_sha256":old_sha,
            "old_verified_matches_quarantined":0,
            "old_verified_kickoff_changed_count":0,
            "events":[],
            "new_hard_holdout_admissions":0,
            "new_clay_holdout_admissions":0,
            "telegram_signal_authorized":False,
            "real_money":"BLOCKED",
        }
    attempt,attempt_sha=_load(recent)
    return compare(old,attempt,old_sha,attempt_sha)

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",default=".")
    a=p.parse_args()
    root=Path(a.root)
    result=run(root,a.date)
    target=root/CAPTURE/a.date/OUT
    target.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in (
        "status","original_verified_match_count",
        "old_verified_matches_quarantined","old_verified_kickoff_changed_count",
        "new_hard_holdout_admissions","new_clay_holdout_admissions")},sort_keys=True))

if __name__=="__main__":
    main()
