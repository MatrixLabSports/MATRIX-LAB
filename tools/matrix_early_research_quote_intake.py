"""Preflight real bookmaker markets up to 24h early, research ONLY.

This does not replace the 120-minute execution window or derive a probability.
If an atomic PIT artifact exists, only a valid immutable snapshot can be used.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

def utc(s):
    d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if d.utcoffset() is None: raise ValueError("EARLY_QUOTE_CLOCK_UNAWARE")
    return d.astimezone(timezone.utc)

def early_targets_from_docs(intake,sofa,flash,now):
    from tools.matrix_football_sofa_fixture_crosscheck import norm
    day=intake.get("target_date_bogota")
    if not isinstance(day,str) or any(x.get("target_date_bogota")!=day for x in (sofa,flash)):
        raise ValueError("EARLY_QUOTE_DATE_CONFLICT")
    if (intake.get("source")!="FOOTBALL_DATA_ORG"
        or intake.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE"
        or not sofa.get("sofascore_observed")
        or sofa.get("status")!="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL"
        or flash.get("status")!="PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
        or flash.get("sofascore_verified") is not True
        or flash.get("flashscore_verified") is not True):
        raise ValueError("EARLY_QUOTE_TRIPLE_SOURCE_UNVERIFIED")
    if any(doc.get("real_money")!="BLOCKED" or doc.get("signal_generation_authorized") is not False
           for doc in (intake,sofa,flash)):
        raise ValueError("EARLY_QUOTE_GOVERNANCE_VIOLATION")
    observed=utc(intake["generated_at_utc"])
    if not 0 <= (utc(now.isoformat())-observed).total_seconds() <= 36*3600:
        raise ValueError("EARLY_QUOTE_SOURCE_STALE")
    src={str(x["source_fixture_id"]):x for x in intake["fixtures"]}
    sf={str(x["fixture_id"]):x for x in sofa["matched"]}
    seen=set();out=[]
    for row in flash["matched"]:
        fid=str(row.get("source_fixture_id") or "")
        a,b=src.get(fid),sf.get(fid)
        if not a or not b: continue
        if (row.get("three_source_calendar_identity_verified") is not True
            or b.get("identity_time_and_teams_verified") is not True
            or b.get("kickoff_utc")!=a.get("kickoff_utc")
            or row.get("kickoff_utc")!=a.get("kickoff_utc")
            or str(row.get("sofascore_event_id"))!=str(b.get("sofascore_event_id"))
            or not row.get("flashscore_mid")): continue
        kickoff=utc(a["kickoff_utc"])
        seconds=(kickoff-utc(now.isoformat())).total_seconds()
        if not 0<seconds<=24*3600:continue
        home,away=(str(a.get(k) or "").strip() for k in ("home","away"))
        if not home or not away or norm(home)==norm(away):continue
        event=(str(b["sofascore_event_id"]),str(row["flashscore_mid"]))
        if event in seen:raise ValueError("EARLY_QUOTE_DUPLICATE_EVENT")
        seen.add(event)
        out.append({"fixture_id":"FOOTBALL_DATA_ORG:"+fid,
          "match":home+" vs "+away,"kickoff":kickoff.isoformat(),
          "p_matrix":None,"research_only":True,
          "preflight_horizon_hours":24,
          "triple_source_calendar_identity_verified":True,
          "production_probability_authorized":False,
          "telegram_signal_authorized":False,
          "sofascore_event_id":event[0],"flashscore_mid":event[1]})
    return sorted(out,key=lambda x:(x["kickoff"],x["fixture_id"]))

def early_targets(now,root:Path):
    from tools.matrix_championship_quote_window_scope import atomic_cycles
    now=utc(now.isoformat())
    today=now.astimezone(timezone(timedelta(hours=-5))).date()
    result=[]
    for offset in (0,1):
        day=(today+timedelta(days=offset)).isoformat()
        folder=root/"evidence"/"football_world_inventory"/day
        atomics=list(folder.glob("MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_*.json"))
        if atomics:
            verified=atomic_cycles(folder,day,now=now)
            if not verified:
                continue  # Never trust mutable fallback over broken atomic evidence.
            _,_,_,docs=max(verified,key=lambda row:(row[0],row[1].name))
            source,sofa,flash=(docs[k] for k in ("intake","sofa","flash"))
        else:
            names=("MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
                "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
                "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json")
            if not all((folder/name).is_file() for name in names):continue
            try:
                source,sofa,flash=(json.loads((folder/name).read_text(encoding="utf-8")) for name in names)
            except (ValueError,OSError):continue
        try:
            result.extend(early_targets_from_docs(source,sofa,flash,now))
        except (ValueError,TypeError,KeyError,OverflowError):continue
    return sorted(result,key=lambda x:(x["kickoff"],x["fixture_id"]))
