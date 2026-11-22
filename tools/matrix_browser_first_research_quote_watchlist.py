"""Research-only browser-first fixture watchlist for authentic quote recovery.

A shadow probability is never an official P_MATRIX and cannot authorize a bet.
An old browser link is NOT a fresh quote or a pre-send fixture crosswalk.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

FREEZE_SCHEMA="MATRIX_ESPN_SIX_LEAGUE_RESEARCH_PROSPECTIVE_OVER25_V1"
BROWSER_SCHEMA="MATRIX_BROWSER_FIRST_ESPN_SOFA_FLASH_PROSPECTIVE_RESEARCH_CROSSWALK_V1"
SCHEMA="MATRIX_BROWSER_FIRST_SHADOW_QUOTE_WATCHLIST_V1"
MAX_BROWSER_AGE_MINUTES=15
FINAL_WINDOW_MINUTES=120


def utc(s):
    x=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError("UNZONED_PREMATCH_CLOCK")
    return x.astimezone(timezone.utc)


def build(browser:dict,freeze:dict,*,now:datetime|None=None)->dict:
    t=now or datetime.now(timezone.utc)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("UNZONED_RESEARCH_CLOCK")
    t=t.astimezone(timezone.utc)
    if (browser.get("schema")!=BROWSER_SCHEMA
        or freeze.get("schema")!=FREEZE_SCHEMA
        or browser.get("source_order")!=["SOFASCORE","FLASHSCORE","ESPN"]
        or browser.get("telegram_signal_authorized") is not False
        or freeze.get("telegram_signal_authorized") is not False
        or browser.get("real_money")!="BLOCKED"
        or freeze.get("real_money")!="BLOCKED"
        or browser.get("odds_market_over_2_5_verified") is not False
        or freeze.get("source_raw_provider_bytes_sha256_verified") is not False):
        raise ValueError("RESEARCH_SOURCE_GOVERNANCE_NOT_TRUSTED")
    report_at=utc(browser["created_from_read_at_utc"])
    if report_at>t:
        raise ValueError("FUTURE_BROWSER_RECEIPT")
    by_id={}
    for row in freeze["rows"]:
        fid=str(row["fixture_id"])
        if fid in by_id:
            raise ValueError("DUPLICATE_FROZEN_ESPN_FIXTURE")
        by_id[fid]=row
    triple=browser.get("three_source_research_match") or {}
    unique=set();rows=[]
    for link in browser["sofascore_match_rows"]:
        eid=str(link.get("espn_fixture_id"))
        sid=str(link.get("sofascore_event_id"))
        key=(eid,sid)
        if key in unique or not sid.isdecimal() or eid not in by_id:
            raise ValueError("AMBIGUOUS_RESEARCH_EVENT_JOIN")
        unique.add(key)
        original=by_id[eid]
        kickoff=utc(original["kickoff_utc"])
        if (utc(link["kickoff_utc"])!=kickoff
            or original["home"]!=link["home_espn"]
            or original["away"]!=link["away_espn"]
            or not link.get("sofascore_url","").startswith("https://www.sofascore.com/es/football/match/")):
            raise ValueError("BROWSER_FIXTURE_ID_OR_KICKOFF_MISMATCH")
        if kickoff<=t:
            continue
        triple_match=(eid==str(triple.get("espn_fixture_id"))
                      and sid==str(triple.get("sofascore_event_id"))
                      and triple.get("flashscore_provider_match_url","").startswith(
                            "https://www.flashscore.co/partido/futbol/"))
        time_to_kickoff=(kickoff-t).total_seconds()/60
        browser_age=(t-report_at).total_seconds()/60
        in_window=0<time_to_kickoff<=FINAL_WINDOW_MINUTES
        browser_recent=browser_age<=MAX_BROWSER_AGE_MINUTES
        eligible=triple_match and in_window and browser_recent
        state=("FRESH_TRIPLE_SOURCE_RESEARCH_QUOTE_LOOKUP_ALLOWED_NOT_SIGNAL" if eligible
               else "WAITING_120M_PREMATCH_WINDOW" if not in_window
               else "WAITING_FRESH_BROWSER_REVALIDATION" if triple_match and not browser_recent
               else "WAITING_FLASHSCORE_EXACT_EVENT_CONFIRMATION")
        rows.append({
            "research_fixture_id":eid,
            "sofascore_event_id":sid,
            "kickoff_utc":kickoff.isoformat(),
            "research_probability_shadow":original["research_probability_over25"],
            "espn_source_raw_sha_verified":False,
            "sofascore_url":link["sofascore_url"],
            "flashscore_url":triple.get("flashscore_provider_match_url") if triple_match else None,
            "three_source_research_calendar_identity":triple_match,
            "browser_receipt_fresh_15m":browser_recent,
            "quote_lookup_window_120m":in_window,
            "research_quote_lookup_eligible":eligible,
            "quote_attempt_state":state,
            "authentic_over25_bookmaker_quote":None,
            "authentic_sharp_reference_quote":None,
            "official_p_matrix":None,
            "positive_governed_ev":None,
            "telegram_signal_authorized":False,
        })
    rows.sort(key=lambda r:(r["kickoff_utc"],r["research_fixture_id"]))
    return {
        "schema":SCHEMA,"status":"RESEARCH_BROWSER_FIRST_WATCHLIST_NOT_PRODUCTION",
        "evaluated_at_utc":t.isoformat(),"browser_receipt_at_utc":report_at.isoformat(),
        "source_order":["SOFASCORE","FLASHSCORE","ESPN"],
        "watchlist_count":len(rows),
        "three_source_calendar_links":sum(r["three_source_research_calendar_identity"] for r in rows),
        "research_quote_lookup_eligible":sum(r["research_quote_lookup_eligible"] for r in rows),
        "pre_send_quote_gate_unchanged":True,
        "requires_fresh_bookmaker_event_over25_quote":True,
        "requires_fresh_sharp_reference":True,
        "requires_governed_official_probability":True,
        "watchlist":rows,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--browser-report",type=Path,required=True)
    p.add_argument("--research-freeze",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"notifications","telegram","daily_prematch_reports","market_portfolio","tennis_signals"}:
        raise SystemExit("RESEARCH_WATCHLIST_MUST_NOT_WRITE_PRODUCTION")
    a=json.loads(args.browser_report.read_text(encoding="utf-8"))
    b=json.loads(args.research_freeze.read_text(encoding="utf-8"))
    report=build(a,b)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"research_watchlist":report["watchlist_count"],
                      "research_quote_lookups":report["research_quote_lookup_eligible"],
                      "green_signals":False}))


if __name__=="__main__":
    main()
