"""Reproduce Over 2.5 research forecasts from two *actually captured* ESPN month archives.

All feature availability is point-in-time: never assert an event's final result
was visible before the observed receipt. Completely isolated from production,
Telegram, bookmaker odds, calibration promotion and real-money wagering.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from tools.matrix_football_espn_enriched_pit_research import LEAGUES, dt

MANIFEST="MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json"
PARAMS={"a":0.6,"b":0.0,"c":0.4}
HISTORY_MIN=5
BASELINE_MIN=20
HISTORY_MAX=20
MAX_RAW_BYTES=2_000_000
SCHEMA="MATRIX_ESPN_SHA_PROVEN_TWO_MONTH_OVER25_RESEARCH_FREEZE_V1"


def read_archive(folder:Path,month:str,lid:str,asof:datetime)->list[dict[str,Any]]:
    report=json.loads((folder/MANIFEST).read_bytes())
    if (report.get("schema")!="MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_CAPTURE_V1"
        or report.get("query_kind")!="MONTH"
        or report.get("day_queried_provider_calendar")!=month
        or report.get("point_in_time_receipts_stamped_after_source_response") is not True
        or report.get("source_league_scope")!=6
        or report.get("production_p_matrix_authorized") is not False
        or report.get("telegram_signal_authorized") is not False
        or report.get("real_money")!="BLOCKED"):
        raise ValueError("UNTRUSTED_SHA_MONTH_RECEIPT")
    src=(report.get("sources") or {}).get(lid) or {}
    slug=LEAGUES[lid]
    if (src.get("status")!="PROVIDER_BYTES_AUTHENTICALLY_CAPTURED_RESEARCH_ONLY"
        or src.get("provider_competition_id")!=slug):
        raise ValueError("MISSING_AUTHENTIC_LEAGUE_SOURCE:"+lid)
    observed=dt(src["source_received_at_utc"])
    if (observed>dt(report["observed_at_utc"]) or observed>asof
        or observed<dt(report["capture_started_at_utc"])):
        raise ValueError("SOURCE_RECEIPT_CLOCK_CONFLICT")
    filename=src.get("raw_archive_file")
    digest=src.get("raw_sha256")
    if (not isinstance(filename,str) or filename!=Path(filename).name
        or not isinstance(digest,str) or len(digest)!=64
        or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("UNSAFE_OR_UNHASHED_SOURCE_FILE")
    path=folder/filename
    if not path.is_file() or path.stat().st_size>MAX_RAW_BYTES:
        raise ValueError("SOURCE_RAW_FILE_MISSING_OR_OVERSIZED")
    raw=path.read_bytes()
    if (len(raw)!=src.get("raw_bytes")
        or hashlib.sha256(raw).hexdigest()!=digest):
        raise ValueError("AUTHENTIC_PROVIDER_BYTES_SHA_MISMATCH")
    body=json.loads(raw)
    if (not isinstance(body,dict) or not isinstance(body.get("events"),list)
        or len(body.get("leagues") or [])!=1
        or body["leagues"][0].get("slug")!=slug):
        raise ValueError("PROVIDER_LEAGUE_ID_OR_SCHEMA_CHANGED")
    result=[]
    seen=set()
    for e in body["events"]:
        if not isinstance(e,dict):
            raise ValueError("SOURCE_EVENT_NOT_OBJECT")
        eid=str(e.get("id") or "")
        if not eid.isdecimal() or eid in seen:
            raise ValueError("DUPLICATE_OR_MISSING_PROVIDER_EVENT_ID")
        seen.add(eid)
        match=(e.get("competitions") or [])
        if len(match)!=1 or not isinstance(match[0],dict):
            raise ValueError("AMBIGUOUS_PROVIDER_FIXTURE")
        m=match[0]
        teams=m.get("competitors") or []
        h=[x for x in teams if isinstance(x,dict) and x.get("homeAway")=="home"]
        a=[x for x in teams if isinstance(x,dict) and x.get("homeAway")=="away"]
        if len(h)!=1 or len(a)!=1:
            raise ValueError("HOME_AWAY_PROVIDER_IDENTITY_AMBIGUOUS")
        hid=str((h[0].get("team") or {}).get("id") or "")
        aid=str((a[0].get("team") or {}).get("id") or "")
        if not hid.isdecimal() or not aid.isdecimal() or hid==aid:
            raise ValueError("PROVIDER_TEAM_IDENTITY_MISSING")
        kickoff=dt(e.get("date"))
        s=(m.get("status") or {}).get("type") or {}
        finalized=(s.get("name")=="STATUS_FULL_TIME" and s.get("completed") is True)
        prematch=(s.get("state")=="pre" and s.get("completed") is False)
        hg,ag=h[0].get("score"),a[0].get("score")
        goals=None
        if finalized:
            if not (str(hg).isdecimal() and str(ag).isdecimal() and kickoff<observed):
                raise ValueError("FINAL_RESULT_NOT_OBSERVED_AFTER_KICKOFF")
            goals=(int(hg),int(ag))
        result.append({"id":eid,"league":lid,"kickoff":kickoff,
                       "home":hid,"away":aid,
                       "home_name":(h[0].get("team") or {}).get("displayName"),
                       "away_name":(a[0].get("team") or {}).get("displayName"),
                       "goals":goals,"prematch":prematch,
                       "received":observed,"raw_sha256":digest})
    return result


def _p_over25(history:list[dict],home:str,away:str)->tuple[float,dict]|None:
    if len(history)<BASELINE_MIN:
        return None
    histories=defaultdict(list)
    for r in history:
        hg,ag=r["goals"]
        histories[r["home"]].append((hg,ag))
        histories[r["away"]].append((ag,hg))
    hp=histories[home][-HISTORY_MAX:]
    ap=histories[away][-HISTORY_MAX:]
    if len(hp)<HISTORY_MIN or len(ap)<HISTORY_MIN:
        return None
    mean=lambda rows,index:sum(x[index] for x in rows)/len(rows)
    lh=min(5.0,max(.05,(mean(hp,0)+mean(ap,1))/2))
    la=min(5.0,max(.05,(mean(ap,0)+mean(hp,1))/2))
    full=over=0.0
    for hg in range(11):
        p_h=math.exp(-lh)*lh**hg/math.factorial(hg)
        for ag in range(11):
            v=p_h*math.exp(-la)*la**ag/math.factorial(ag)
            full+=v
            if hg+ag>=3:
                over+=v
    poisson=over/full
    baseline=sum(sum(r["goals"])>=3 for r in history)/len(history)
    clip=lambda p:max(1e-12,min(1.0-1e-12,p))
    logit=lambda p:math.log(clip(p)/(1.0-clip(p)))
    z=PARAMS["a"]*logit(poisson)+PARAMS["c"]*logit(baseline)+PARAMS["b"]
    p=(1/(1+math.exp(-z))) if z>=0 else math.exp(z)/(1+math.exp(z))
    return round(p,10),{"home_history_count":len(hp),"away_history_count":len(ap),
                        "group_history_count":len(history),
                        "poisson_over25":round(poisson,10),
                        "group_baseline_over25":round(baseline,10),
                        "home_lambda":round(lh,8),"away_lambda":round(la,8)}


def evaluate(october:Path,november:Path,*,frozen_at:datetime|None=None)->dict:
    now=frozen_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("FREEZE_TIME_MUST_BE_AWARE")
    now=now.astimezone(timezone.utc)
    month_dirs=(("2026-10",october),("2026-11",november))
    rows=[];blocked=[];counts={}
    for lid,slug in LEAGUES.items():
        by_id={}
        for month,folder in month_dirs:
            for event in read_archive(folder,month,lid,now):
                old=by_id.setdefault(event["id"],[])
                if old and any((q["kickoff"]!=event["kickoff"]
                                or q["home"]!=event["home"]
                                or q["away"]!=event["away"]) for q in old):
                    raise ValueError("CROSS_MONTH_PROVIDER_FIXTURE_IDENTITY_CONFLICT")
                old.append(event)
        # Historical final results first visible in a verified receipt.
        history=[];future=[]
        for eid,versions in by_id.items():
            results=sorted((x for x in versions if x["goals"] is not None
                            and x["received"]<=now),key=lambda x:x["received"])
            if results:
                first=results[0]
                if any(x["goals"]!=first["goals"] for x in results):
                    raise ValueError("CHANGED_FINAL_SCORE_ACROSS_SOURCE_ARCHIVES")
                history.append(first)
            available=sorted((x for x in versions if x["prematch"]
                              and x["received"]<x["kickoff"]
                              and x["received"]<=now
                              and x["kickoff"]>now),key=lambda x:x["received"])
            if available:
                future.append(available[0])
        history.sort(key=lambda r:(r["kickoff"],r["id"]))
        futures=sorted(future,key=lambda r:(r["kickoff"],r["id"]))
        admitted=0
        for target in futures:
            past=[r for r in history if r["kickoff"]<target["kickoff"]
                  and r["received"]<=now]
            calc=_p_over25(past,target["home"],target["away"])
            if calc is None:
                blocked.append({"league":lid,"event_id":target["id"],
                                "reason":"NOT_ENOUGH_VERIFIED_RAW_GROUP_OR_TEAM_HISTORY"})
                continue
            probability,features=calc
            # A source receipt cannot come after the frozen forecast or kickoff.
            assert all(r["received"]<=now and r["kickoff"]<now for r in past)
            rows.append({
                "provider":"ESPN_PUBLIC_SCOREBOARD_JSON",
                "provider_fixture_id":target["id"],
                "original_league_id_research_only":lid,
                "provider_league":slug,
                "home_provider_team_id":target["home"],
                "away_provider_team_id":target["away"],
                "home":target["home_name"],"away":target["away_name"],
                "kickoff_utc":target["kickoff"].isoformat(),
                "research_frozen_at_utc":now.isoformat(),
                "target_source_sha256":target["raw_sha256"],
                "target_source_received_at_utc":target["received"].isoformat(),
                "historic_source_sha256":[
                     {"event_id":r["id"],"raw_sha256":r["raw_sha256"],
                      "first_observed_at_utc":r["received"].isoformat()}
                     for r in past],
                "source_history_feature_trace":features,
                "research_probability_over25":probability,
                "observed_outcome":None,
                "official_original_p_matrix_authorized":False,
                "telegram_signal_authorized":False})
            admitted+=1
        counts[lid]={"provider_league":slug,
                     "distinct_prior_final_events":len(history),
                     "future_provider_events":len(futures),
                     "sha_and_pit_verified_research_probabilities":admitted}
    return {"schema":SCHEMA,
            "status":"AUTHENTIC_SOURCE_SHA_AND_PIT_RESEARCH_MATH_REPLAY_NO_PROMOTION",
            "research_frozen_at_utc":now.isoformat(),
            "frozen_math_parameters":dict(PARAMS),
            "model_frozen_parameters_modified":False,
            "source_months":["2026-10","2026-11"],
            "source_priority":["SOFASCORE","FLASHSCORE","ESPN"],
            "source_provider":"ESPN_PUBLIC_SCOREBOARD_JSON",
            "source_sha256_and_point_in_time_receipts_verified":True,
            "six_league_counts":counts,"research_rows":rows,"blocked":blocked,
            "research_probability_count":len(rows),
            "science_out_of_sample_certified":False,
            "original_enriched_api_football_equivalence_certified":False,
            "original_p_matrix_reinstated":False,
            "production_p_matrix_authorized":False,
            "telegram_signal_authorized":False,
            "automatic_wagering":False,"real_money":"BLOCKED"}


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--october",type=Path,required=True)
    p.add_argument("--november",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"telegram","notifications","governance","daily_prematch_reports","tennis_signals"}:
        raise SystemExit("RESEARCH_PRODUCER_CANNOT_WRITE_PRODUCTION")
    report=evaluate(args.october,args.november)
    out=args.out
    if out.exists():
        raise SystemExit("IMMUTABLE_RESEARCH_FREEZE_ALREADY_EXISTS")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"sha_pit_research_probability_count":report["research_probability_count"],
                      "source_sha_verified":True,"production_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
