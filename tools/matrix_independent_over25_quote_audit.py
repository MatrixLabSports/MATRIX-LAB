"""Read-only independent Over 2.5 price audit with quota and 120-second fail-closed gates.

This NEVER emits Telegram, creates production signal files, or changes
calibrated predictions. odds-api.net requests are forbidden unless its live
usage endpoint confirms remaining quota and the event is within the governed
120-minute prematch window.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS, classify_bookmaker
from tools.odds_api_quota_guard import evaluate_usage
from tools.football_clv_odds_api_net_capture import _sim, _exact_line_from_item, _is_standard_goal_total

BASE = "https://api.odds-api.net/v1"
MAX_MATCHES_PER_CYCLE = 3
MAX_SEARCH_WINDOW_MINUTES = 120
QUOTE_FRESH_SECONDS = 120
BOOK_KEYS = sorted({alias for aliases in EXECUTION_BOOKMAKERS.values() for alias in aliases} | {"pinnacle"})

def utc(value):
    v = datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if v.utcoffset() is None: raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    return v.astimezone(timezone.utc)

def digest(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def match_event(fixture, event_rows):
    candidates=[]
    for event in event_rows:
        if not isinstance(event,dict) or not event.get("event_id"):continue
        direct_home=_sim(fixture["home"],event.get("home_team"))
        direct_away=_sim(fixture["away"],event.get("away_team"))
        swapped=(_sim(fixture["home"],event.get("away_team"))+_sim(fixture["away"],event.get("home_team")))/2
        if direct_home < 0.82 or direct_away < 0.82:
            continue
        direct=(direct_home+direct_away)/2
        if direct<=swapped+0.10:continue
        candidates.append((direct,event))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates:return None, "NO_EXACT_DIRECT_TEAM_IDENTITY"
    if len(candidates)>1 and candidates[0][0]-candidates[1][0]<0.10:
        return None,"AMBIGUOUS_PROVIDER_EVENT_IDENTITY"
    return candidates[0][1],"MATCHED_TEAMS_ODDS_EVENT"

def _price_rows(snapshot, now):
    ts=(snapshot.get("bookmaker_as_of_ts_ms") or {})
    out=[]
    for item in snapshot.get("items") or []:
        if not isinstance(item,dict) or item.get("is_available") is not True:continue
        house=str(item.get("bookmaker") or "").strip().casefold()
        if house not in BOOK_KEYS:continue
        try:
            line=_exact_line_from_item(item)
            value=float(item.get("odds"))
            if not (line==2.5 and math.isfinite(value) and value>1.0 and _is_standard_goal_total(item)):
                continue
            label=str(item.get("side") or "")+" "+str(item.get("selection_name") or "")
            if "over" not in label.casefold() or "under" in label.casefold():continue
            period=str(item.get("period_str") or item.get("period") or "").strip().casefold()
            if period not in ("full time","full_time","fulltime","ft","0","regular time","regular_time"):
                continue
            timestamp=ts.get(house)
            if isinstance(timestamp,bool) or not isinstance(timestamp,(float,int)):continue
            age=(now-datetime.fromtimestamp(timestamp/1000,tz=timezone.utc)).total_seconds()
            if not 0<=age<=QUOTE_FRESH_SECONDS:continue
        except (ValueError,OverflowError,TypeError):
            continue
        if house!="pinnacle":
            classified=classify_bookmaker(house)
            if not classified.execution_eligible:continue
        out.append({"house":house,"is_sharp_reference":house=="pinnacle",
                    "decimal_odds":round(value,6),"provider_quote_age_seconds":round(age,2),
                    "provider_quote_updated_at_utc":datetime.fromtimestamp(timestamp/1000,tz=timezone.utc).isoformat(),
                    "market":"FULL_TIME_TOTAL_GOALS_OVER_2_5"})
    return out

def audit(intake,shadow,key,*,session=None,now=None,max_matches=MAX_MATCHES_PER_CYCLE,probe_quota_outside_window=False,previous=None):
    if intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1" or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1":
        raise ValueError("UNTRUSTED_INDEPENDENT_INPUTS")
    if intake.get("target_date_bogota")!=shadow.get("target_date_bogota"):
        raise ValueError("FIXTURE_SCORE_DATE_MISMATCH")
    if intake.get("signal_generation_authorized") is not False or shadow.get("market_signal_authorized") is not False:
        raise ValueError("INPUT_PROMOTION_FORBIDDEN")
    if intake.get("real_money")!="BLOCKED" or shadow.get("real_money")!="BLOCKED":
        raise ValueError("REAL_MONEY_MUST_REMAIN_BLOCKED")
    if not (0<=max_matches<=MAX_MATCHES_PER_CYCLE):
        raise ValueError("INVALID_NETWORK_BUDGET")
    clock=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result={"schema":"MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT_V1",
            "target_date_bogota":intake["target_date_bogota"],
            "generated_at_utc":clock.isoformat(),
            "status":"BLOCKED_QUOTES_NOT_CERTIFIED",
            "network_calls":0,"quota_status":"NOT_CHECKED",
            "audited":[],"decisions":[],
            "bookmaker_quote_verified_count":0,
            "sharp_120s_verified_count":0,
            "independent_match_count":0,
            "provider_source_equivalence_verified":False,
            "browser_first_reconciliation_verified":False,
            "production_calibration_parity_verified":False,
            "signal_generation_authorized":False,
            "telegram_messages_sent":0,
            "automatic_wagering":False,
            "real_money":"BLOCKED"}
    scores={str(x.get("source_fixture_id")):x for x in (shadow.get("scored") or []) if isinstance(x,dict)}
    in_window=[]
    for row in intake.get("fixtures") or []:
        if not isinstance(row,dict):continue
        fid=str(row.get("source_fixture_id") or "")
        try:
            kickoff=utc(row["kickoff_utc"])
        except (ValueError,KeyError,TypeError):
            continue
        if not 0<(kickoff-clock).total_seconds()<=MAX_SEARCH_WINDOW_MINUTES*60:
            continue
        score=scores.get(fid)
        if not score or score.get("kickoff_utc")!=row["kickoff_utc"]:
            continue
        in_window.append((kickoff,row,score))
    in_window.sort(key=lambda x:(x[0],str(x[1]["source_fixture_id"])))
    result["in_120m_window"]=len(in_window)
    result["eligible_for_price_attempt"]=min(len(in_window),max_matches)
    if (not in_window or max_matches==0) and not probe_quota_outside_window:
        result["quota_status"]="SKIPPED_NO_PREMATCH_WINDOW"
        result["status"]="WAITING_FOR_GOVERNED_PREMATCH_WINDOW"
        return result
    if in_window and isinstance(previous,dict) and previous.get("target_date_bogota")==result["target_date_bogota"]:
        if previous.get("quota_status") in ("BLOCKED_USAGE_HTTP_429","BLOCKED_EXHAUSTED","BLOCKED_COOLDOWN_AFTER_429"):
            try:
                elapsed=(clock-utc(previous["generated_at_utc"])).total_seconds()
                if 0 <= elapsed < 3600:
                    result["quota_status"]="BLOCKED_COOLDOWN_AFTER_429"
                    result["status"]="WAITING_FOR_PROVIDER_QUOTA_CIRCUIT_BREAKER"
                    return result
            except (ValueError,TypeError,KeyError):
                pass
    key = str(key or "").strip()
    if not key:
        result["quota_status"]="MISSING_ODDS_API_NET_KEY"
        return result
    if any(ord(c) < 33 or ord(c) > 126 for c in key):
        result["quota_status"]="BLOCKED_INVALID_KEY_HEADER_FORMAT"
        return result
    session=session or requests.Session()
    headers={"X-API-Key":key,"Accept":"application/json"}
    try:
        u=session.get(BASE+"/usage",headers=headers,timeout=(5,15))
        result["network_calls"]+=1
        if int(u.status_code)!=200:
            result["quota_status"]="BLOCKED_USAGE_HTTP_"+str(u.status_code)
            return result
        usage=u.json()
        if not isinstance(usage,dict):
            result["quota_status"]="BLOCKED_USAGE_PAYLOAD"
            return result
        decision=evaluate_usage(usage)
        result["quota_stage"]=decision["stage"]
        if not decision["api_calls_allowed"]:
            result["quota_status"]="BLOCKED_EXHAUSTED"
            return result
        result["quota_status"]="AUTHORIZED_LIVE_USAGE"
    except (requests.RequestException,TypeError,ValueError,KeyError) as exc:
        result["quota_status"]="BLOCKED_USAGE_"+type(exc).__name__
        return result
    if not in_window or max_matches==0:
        result["status"]="WAITING_FOR_GOVERNED_PREMATCH_WINDOW"
        return result
    for kickoff,row,score in in_window[:max_matches]:
        item={"source_fixture_id":row["source_fixture_id"],"home":row["home"],
              "away":row["away"],"kickoff_utc":row["kickoff_utc"],
              "identity_status":"BLOCKED","quotes":[],"p_over25_research":score.get("p_over25_research"),
              "research_edge_only":True,"telegram_authorized":False}
        try:
            t=int(kickoff.timestamp())
            er=session.get(BASE+"/events",headers=headers,params={"sport":"soccer",
                        "start_from":t-900,"start_to":t+900,"limit":100,
                        "include_bookmaker_ids":"true"},timeout=(5,15))
            result["network_calls"]+=1
            item["events_http_status"]=int(er.status_code)
            if er.status_code!=200:
                item["identity_status"]="BLOCKED_EVENT_HTTP_"+str(er.status_code)
                result["audited"].append(item)
                if er.status_code==429:break
                continue
            ep=er.json()
            if not isinstance(ep,dict) or not isinstance(ep.get("items"),list) or ep.get("next_cursor"):
                item["identity_status"]="BLOCKED_EVENT_PAGE_INCOMPLETE"
                result["audited"].append(item)
                continue
            event,identity=match_event(row,ep["items"])
            item["event_response_sha256"]=digest(ep)
            item["identity_status"]=identity
            if event is None:
                result["audited"].append(item);continue
            result["independent_match_count"]+=1
            event_id=str(event["event_id"])
            sr=session.get(BASE+"/events/"+event_id+"/odds/snapshot",headers=headers,
                           params={"bookmakers":",".join(BOOK_KEYS),"types":"total",
                                   "periods":"full time","include_source":"true",
                                   "include_unavailable":"true"},timeout=(5,15))
            result["network_calls"]+=1
            observed=datetime.now(timezone.utc) if now is None else clock
            item["snapshot_http_status"]=int(sr.status_code)
            if sr.status_code!=200:
                item["identity_status"]="BLOCKED_SNAPSHOT_HTTP_"+str(sr.status_code)
                result["audited"].append(item)
                if sr.status_code==429:break
                continue
            sp=sr.json()
            if not isinstance(sp,dict) or not isinstance(sp.get("items"),list) or (sp.get("event_id") not in (None,"",event_id)) :
                item["identity_status"]="BLOCKED_INVALID_SNAPSHOT"
                result["audited"].append(item);continue
            item["snapshot_sha256"]=digest(sp)
            quotes=_price_rows(sp,observed)
            sharp=[x for x in quotes if x["is_sharp_reference"]]
            execution=[x for x in quotes if not x["is_sharp_reference"] and x["decimal_odds"]>1.50]
            item["quotes"]=quotes
            item["sharp_reference_fresh"]=bool(sharp)
            item["physical_book_quote_fresh"]=bool(execution)
            if sharp:result["sharp_120s_verified_count"]+=1
            if execution:result["bookmaker_quote_verified_count"]+=1
            if execution and sharp:
                odds=max(execution,key=lambda x:x["decimal_odds"])
                p=score.get("p_over25_research")
                try:
                    p=float(p);ev=p*odds["decimal_odds"]-1
                except (TypeError,ValueError):
                    p,ev=None,None
                item["best_execution_quote"]=odds
                item["research_ev"]=round(ev,6) if ev is not None else None
                item["research_quality_gate_pass"]=bool(p is not None and p>=0.6 and ev is not None and ev>=0.05)
                item["identity_status"]="RESEARCH_QUOTE_PAIRED_NO_CALIBRATION_PARITY"
            result["audited"].append(item)
        except (requests.RequestException,ValueError,TypeError,KeyError,OverflowError) as exc:
            item["identity_status"]="BLOCKED_PROVIDER_"+type(exc).__name__
            result["audited"].append(item)
    result["status"]="READ_ONLY_QUOTE_AUDIT_COMPLETED_NO_TELEGRAM"
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--intake",type=Path,required=True)
    parser.add_argument("--shadow",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--probe-quota-outside-window",action="store_true")
    parser.add_argument("--previous",type=Path)
    a=parser.parse_args()
    data=lambda p:json.loads(p.read_text(encoding="utf-8"))
    previous=data(a.previous) if a.previous and a.previous.is_file() else None
    result=audit(data(a.intake),data(a.shadow),os.environ.get("ODDS_API_NET_KEY",""),
                 previous=previous,probe_quota_outside_window=a.probe_quota_outside_window)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "status","network_calls","quota_status","independent_match_count",
        "bookmaker_quote_verified_count","sharp_120s_verified_count","signal_generation_authorized"
    )},sort_keys=True))
if __name__=="__main__":main()
