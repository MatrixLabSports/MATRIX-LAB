"""Secondary independent source: ESPN MLS official-score feed, strict identity.

Research-only source. ESPN ID is kept separate from API-Football. Only 90-minute
completed matches with exact UTC kickoff and unique home/away teams. No guessed
halftime from goal incidents; no mutation of canonical settled ledgers.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from tools.matrix_13_cohort_independent_results import dt, normalized

ROOT=Path(__file__).resolve().parents[1]
TRIAGE=ROOT/"evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"
DIR=ROOT/"evidence/football_cohort_recovery"
OUT=DIR/"MATRIX_ESPN_MLS_EXACT_FINAL_LAST.json"
SOURCE="https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"
BOGOTA=ZoneInfo("America/Bogota")
MAX_BYTES=3_000_000


def club(name):
    tokens=normalized(name).split()
    if tokens and tokens[0] in {"fc","cf","sc"}:
        tokens=tokens[1:]
    if tokens and tokens[-1] in {"fc","cf","sc"}:
        tokens=tokens[:-1]
    if not tokens:
        raise ValueError("EMPTY_NORMALIZED_CLUB")
    return " ".join(tokens)


def _event(event):
    if not isinstance(event,dict):
        return None
    comps=event.get("competitions")
    if not isinstance(comps,list) or len(comps)!=1:
        return None
    comp=comps[0]
    status=comp.get("status") or {}
    typ=status.get("type") or {}
    if (typ.get("name")!="STATUS_FULL_TIME" or typ.get("completed") is not True
        or int(status.get("period") or 0)!=2):
        return None
    teams=comp.get("competitors")
    if not isinstance(teams,list) or len(teams)!=2:
        return None
    sides={}
    for team in teams:
        side=team.get("homeAway")
        if side not in ("home","away") or side in sides:
            return None
        score=team.get("score")
        if not isinstance(score,str) or not score.isdigit():
            return None
        sides[side]=dict(name=team["team"]["displayName"],score=int(score))
    if set(sides)!={"home","away"}:
        return None
    return {"id":str(event["id"]),"kickoff_utc":dt(event["date"]).isoformat(),
            "home_name":sides["home"]["name"],"away_name":sides["away"]["name"],
            "home_goals":sides["home"]["score"],"away_goals":sides["away"]["score"]}


def compare(rows,payload,raw_sha):
    if not isinstance(payload,dict) or not isinstance(payload.get("events"),list):
        raise ValueError("ESPN_EVENTS_MISSING")
    indexed={}
    for row in payload["events"]:
        try:
            event=_event(row)
            if not event:
                continue
            key=(event["kickoff_utc"],club(event["home_name"]),club(event["away_name"]))
            indexed.setdefault(key,[]).append(event)
        except (ValueError,TypeError,KeyError):
            continue
    accepted=[]; blocked=[]
    for row in rows:
        fid=str(row.get("fixture_id") or "")
        try:
            start=dt(row["kickoff_utc"])
            freeze=dt(row["freeze_at_utc"])
            if not fid or freeze>=start:
                raise ValueError("INVALID_FREEZE")
            key=(start.isoformat(),club(row["home_team_name"]),club(row["away_team_name"]))
        except (ValueError,TypeError,KeyError):
            blocked.append({"fixture_id":fid,"reason":"BAD_FROZEN_IDENTITY"})
            continue
        candidates=indexed.get(key,[])
        if len(candidates)!=1:
            blocked.append({"fixture_id":fid,"reason":"NO_UNIQUE_EXACT_ESPN_MATCH"})
            continue
        match=candidates[0]
        accepted.append({
            "api_football_fixture_id":fid,
            "api_football_kickoff_utc":start.isoformat(),
            "frozen_home":row["home_team_name"],
            "frozen_away":row["away_team_name"],
            "independent_source":"ESPN_MLS",
            "espn_fixture_id":match["id"],
            "espn_home":match["home_name"],"espn_away":match["away_name"],
            "fulltime_home":match["home_goals"],"fulltime_away":match["away_goals"],
            "half_time_certified":False,
            "raw_espn_response_sha256":raw_sha,
            "immutable_prematch_prediction":True,
            "canonical_ledger_appends":0,
            "telegram_authorized":False,
        })
    return accepted,blocked


def run(rows,*,opener=urlopen):
    queue=[x for x in rows if x.get("competition_name")=="Major League Soccer"]
    days=sorted(set(dt(x["kickoff_utc"]).astimezone(BOGOTA).strftime("%Y%m%d") for x in queue))
    report={
        "schema":"MATRIX_ESPN_MLS_EXACT_FINAL_V1",
        "status":"NO_MLS_QUEUE" if not queue else "STARTED",
        "source":"ESPN_MLS","source_priority":["SOFASCORE","FLASHSCORE","ALTERNATE_FINAL_VERIFICATION"],
        "queue_count":len(queue),"days_checked":days,
        "network_calls":0,"exact_final_matches":0,"matches":[],"rejected":[],
        "canonical_ledger_appends":0,"telegram_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }
    raw_responses={}
    if len(days)>3:
        report["status"]="TOO_MANY_DATES"
        return report,raw_responses
    for day in days:
        uri=SOURCE+"?dates="+day
        report["network_calls"]+=1
        try:
            req=Request(uri,headers={"Accept":"application/json","User-Agent":"MATRIX-Coherence-Audit/1.0"})
            with opener(req,timeout=25) as resp:
                status=int(resp.status)
                body=resp.read(MAX_BYTES+1)
            if status!=200 or len(body)>MAX_BYTES:
                report["rejected"].append({"day":day,"reason":"HTTP_ERROR_OR_TOO_LARGE","http":status})
                continue
            payload=json.loads(body)
            digest=hashlib.sha256(body).hexdigest()
            archive="ESPN_MLS_"+day+"_RAW.json"
            matched,rejected=compare(
                [r for r in queue if dt(r["kickoff_utc"]).astimezone(BOGOTA).strftime("%Y%m%d")==day],
                payload,digest,
            )
            for row in matched:
                row["raw_archive_path"]="evidence/football_cohort_recovery/"+archive
            report["matches"].extend(matched)
            report["rejected"].extend(rejected)
            report.setdefault("provider_response_hashes",{})[day]=digest
            report.setdefault("provider_events_seen",{})[day]=len(payload["events"])
            raw_responses[archive]=body
        except HTTPError as e:
            report["rejected"].append({"day":day,"reason":"ESPN_HTTP_ERROR","http":e.code})
        except (URLError,TimeoutError,OSError):
            report["rejected"].append({"day":day,"reason":"ESPN_NETWORK_ERROR"})
        except (ValueError,UnicodeError,KeyError,TypeError):
            report["rejected"].append({"day":day,"reason":"ESPN_SCHEMA_INVALID"})
    report["exact_final_matches"]=len(report["matches"])
    report["status"]="VERIFIED_INDEPENDENT_RESEARCH_ONLY" if report["matches"] else "NO_EXACT_FINAL_VERIFIED"
    return report,raw_responses


def main():
    t=json.loads(TRIAGE.read_text(encoding="utf-8"))
    if t.get("target_market_count")!=13 or t.get("protections",{}).get("real_money")!="BLOCKED":
        raise SystemExit("UNTRUSTED_PREMATCH_TRIAGE")
    report,raw=run(t["unsettled_fixture_triage"])
    DIR.mkdir(parents=True,exist_ok=True)
    for archive,body in raw.items():
        dest=DIR/archive
        dest.write_bytes(body)
    OUT.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"queue":report["queue_count"],
        "matched":report["exact_final_matches"],"days":report["days_checked"],
        "provider_events":report.get("provider_events_seen"),"calls":report["network_calls"]},sort_keys=True))


if __name__=="__main__":
    main()
