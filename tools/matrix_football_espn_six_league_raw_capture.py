"""Six-league ESPN public raw+enriched historical evidence, strictly research-only.

SofaScore and Flashscore retain source-priority for operational matching;
this endpoint is an independent auxiliary source and never authorizes betting.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from tools.matrix_football_espn_enriched_pit_research import LEAGUES,extract,dt,MAX_BYTES

URL="https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={period}&limit={limit}"
SCHEMA="MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_CAPTURE_V1"


def capture(day: str, *, opener=urlopen, observed_at:datetime|None=None):
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}",day):
        date.fromisoformat(day+"-01")
        query_kind="MONTH"
        limit=300
    elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",day):
        date.fromisoformat(day)
        query_kind="DAY"
        limit=30
    else:
        raise ValueError("ESPN_PERIOD_MUST_BE_ISO_DAY_OR_MONTH")
    when=observed_at or datetime.now(timezone.utc)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("CAPTURE_CLOCK_REQUIRES_TIMEZONE")
    observed=when.astimezone(timezone.utc).isoformat()
    captured={}; raw_files={}
    for lid,slug in LEAGUES.items():
        endpoint=URL.format(slug=slug,period=day.replace("-",""),limit=limit)
        try:
            request=Request(endpoint,headers={"Accept":"application/json"})
            with opener(request,timeout=20) as res:
                if int(res.status)!=200:
                    raise ValueError("ESPN_HTTP_NON_200")
                raw=res.read(MAX_BYTES+1)
            digest=hashlib.sha256(raw).hexdigest()
            # Do NOT stamp a response with the request's start time: data
            # availability is evidenced only after response bytes arrived.
            source_received_at=(observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
            history=extract(raw,raw_sha256=digest,observed_at_utc=source_received_at,
                            original_league_id=lid)
            raw_files[lid]=raw
            captured[lid]={
                "provider_competition_id":slug,
                "status":"PROVIDER_BYTES_AUTHENTICALLY_CAPTURED_RESEARCH_ONLY",
                "source_url":endpoint,"raw_sha256":digest,"raw_bytes":len(raw),
                "source_received_at_utc":source_received_at,
                "provider_final_history_count":history["verified_source_event_count"],
                "fully_enriched_history_count":history["fully_enriched_event_count"],
                "rejected_or_not_final_count":len(history["rejected_or_not_final_events"]),
                "history":history
            }
        except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError,UnicodeError,KeyError) as exc:
            captured[lid]={
                "provider_competition_id":slug,
                "status":"SOURCE_CAPTURE_BLOCKED_NO_ZERO_IMPUTATION",
                "source_url":endpoint,
                "reason":type(exc).__name__,
                "provider_final_history_count":None,
                "fully_enriched_history_count":None,
            }
    return ({
        "schema":SCHEMA,
        "source":"ESPN_PUBLIC_SCOREBOARD_JSON",
        "day_queried_provider_calendar":day,
        "query_kind":query_kind,
        "backfilled_monthly_results_are_not_prospective_predictions":True,
        "observed_at_utc":(observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "capture_started_at_utc":observed,
        "point_in_time_receipts_stamped_after_source_response":True,
        "source_priority":["SOFASCORE","FLASHSCORE","ESPN"],
        "browser_first_crossmatch_completed":False,
        "utc_calendar_day_is_not_complete_bogota_day":True,
        "source_captured_leagues":len(raw_files),
        "source_league_scope":len(LEAGUES),
        "sources":captured,
        "source_ids_are_not_api_football_fixture_ids":True,
        "original_feature_equivalence_certified":False,
        "scientific_oos_calibration_certified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED"}, raw_files)


def persist(out:Path,report:dict,raws:dict[str,bytes]):
    if set(out.parts) & {"telegram","notifications","governance","daily_prematch_reports"}:
        raise ValueError("RAW_RESEARCH_NOT_PRODUCTION")
    out.mkdir(parents=True,exist_ok=True)
    for lid,raw in raws.items():
        entry=report["sources"][lid]
        digest=hashlib.sha256(raw).hexdigest()
        if digest != entry["raw_sha256"] or len(raw) != entry["raw_bytes"]:
            raise ValueError("CAPTURE_BYTES_DONT_MATCH_RECEIPT")
        path=out/("ESPN_"+entry["provider_competition_id"].replace(".","_")+"_"+digest+".json")
        if path.exists() and path.read_bytes()!=raw:
            raise ValueError("IMMUTABLE_SOURCE_HASH_CONFLICT")
        if not path.exists():
            path.write_bytes(raw)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError("RAW_SOURCE_PERSISTENCE_INVALID")
        entry["raw_archive_file"]=path.name
    (out/"MATRIX_ESPN_SIX_LEAGUE_RAW_RESEARCH_LAST.json").write_text(
        json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")


def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--day",help="Single provider calendar date YYYY-MM-DD")
    group.add_argument("--month",help="Historical league month YYYY-MM; results are never backfilled predictions")
    p.add_argument("--out",type=Path,default=Path("evidence/research/football_six_league_espn"))
    a=p.parse_args()
    report,raws=capture(a.month or a.day)
    persist(a.out,report,raws)
    print(json.dumps({"captured_leagues":report["source_captured_leagues"],
                      "final_historical_rows":sum(x["provider_final_history_count"] or 0
                          for x in report["sources"].values()),
                      "signals":False,"real_money":"BLOCKED"},sort_keys=True))

if __name__=="__main__":
    main()
