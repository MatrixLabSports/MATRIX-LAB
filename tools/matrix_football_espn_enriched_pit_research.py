"""Strict SHA-bound ESPN football historical enrichment, research-only.

Historical observations become eligible for a *later* forecast only when their
captured-at receipt is earlier than that forecast's frozen-at timestamp.
No reconstructed odds, P_MATRIX, or betting signal is produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

LEAGUES = {"39":"eng.1","61":"fra.1","78":"ger.1",
           "135":"ita.1","140":"esp.1","239":"col.1"}
STAT_FIELDS = ("totalShots","shotsOnTarget","wonCorners","foulsCommitted",
               "possessionPct")
INT_STATS = set(STAT_FIELDS) - {"possessionPct"}
MAX_BYTES = 2_000_000


def dt(value: object) -> datetime:
    if not isinstance(value,str):
        raise ValueError("SOURCE_TIMESTAMP_MISSING")
    instant = datetime.fromisoformat(value.replace("Z","+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("SOURCE_TIMESTAMP_UNZONED")
    return instant.astimezone(timezone.utc)


def number(value: object, *, percent: bool=False) -> float | int | None:
    if value is None:
        return None
    if not isinstance(value,str) or value == "":
        return None
    try:
        n=float(value)
    except ValueError:
        return None
    if not math.isfinite(n) or n < 0:
        return None
    if percent:
        return n if n<=100 else None
    return int(n) if n.is_integer() else None


def side(comp: dict, side_name: str) -> dict:
    candidates=[c for c in (comp.get("competitors") or [])
                if isinstance(c,dict) and c.get("homeAway")==side_name]
    if len(candidates)!=1:
        raise ValueError("ESPN_HOME_AWAY_IDENTITY_AMBIGUOUS")
    c=candidates[0]
    team=c.get("team") or {}
    tid=str(team.get("id") or "")
    if not tid.isdigit() or not team.get("displayName"):
        raise ValueError("ESPN_TEAM_IDENTITY_INVALID")
    score=number(c.get("score"))
    if score is None:
        raise ValueError("ESPN_FINAL_SCORE_INVALID")
    stats={}
    for item in c.get("statistics") or []:
        if not isinstance(item,dict):
            raise ValueError("ESPN_STATS_ROW_INVALID")
        key=item.get("name")
        if key not in STAT_FIELDS:
            continue
        if key in stats:
            raise ValueError("ESPN_DUPLICATE_STAT_FIELD")
        stats[key]=number(item.get("displayValue"),percent=key=="possessionPct")
    stats={key:stats.get(key) for key in STAT_FIELDS}
    shots,ontarget=stats["totalShots"],stats["shotsOnTarget"]
    if shots is not None and ontarget is not None and ontarget>shots:
        raise ValueError("ESPN_ON_TARGET_EXCEEDS_SHOTS")
    return {"team_id":tid,"team_name":team["displayName"],
            "final_goals":score,"stats":stats,
            "all_five_stats_present":all(v is not None for v in stats.values())}


def extract(raw: bytes, *, raw_sha256: str, observed_at_utc: str,
            original_league_id: str) -> dict:
    if len(raw)>MAX_BYTES or len(raw)==0:
        raise ValueError("RAW_SOURCE_SIZE_INVALID")
    if hashlib.sha256(raw).hexdigest()!=raw_sha256:
        raise ValueError("RAW_SOURCE_SHA256_MISMATCH")
    league=LEAGUES.get(str(original_league_id))
    if league is None:
        raise ValueError("LEAGUE_OUTSIDE_GOVERNED_SIX")
    observed=dt(observed_at_utc)
    payload=json.loads(raw)
    if not isinstance(payload,dict) or not isinstance(payload.get("events"),list):
        raise ValueError("ESPN_PROVIDER_JSON_SCHEMA_INVALID")
    headers=payload.get("leagues") or []
    if len(headers)!=1 or headers[0].get("slug")!=league:
        raise ValueError("ESPN_COMPETITION_NAMESPACE_MISMATCH")
    rows=[]
    ids=set()
    blocked=[]
    for e in payload["events"]:
        try:
            if not isinstance(e,dict):
                raise ValueError("ESPN_EVENT_NOT_OBJECT")
            event_id=str(e.get("id") or "")
            if not event_id.isdigit() or event_id in ids:
                raise ValueError("ESPN_EVENT_ID_MISSING_OR_DUPLICATE")
            ids.add(event_id)
            kickoff=dt(e.get("date"))
            competition=e.get("competitions") or []
            if len(competition)!=1:
                raise ValueError("ESPN_COMPETITION_ROW_AMBIGUOUS")
            comp=competition[0]
            status=(comp.get("status") or {}).get("type") or {}
            if (status.get("name")!="STATUS_FULL_TIME"
                or status.get("completed") is not True
                or kickoff>=observed):
                raise ValueError("EVENT_NOT_AUTHENTICALLY_FINAL_AT_OBSERVATION")
            home=side(comp,"home")
            away=side(comp,"away")
            if home["team_id"]==away["team_id"]:
                raise ValueError("HOME_AND_AWAY_SAME_PROVIDER_TEAM")
            rows.append({"provider":"ESPN_PUBLIC_SCOREBOARD_JSON",
                         "provider_competition_id":league,
                         "original_league_id_research_mapping":str(original_league_id),
                         "provider_event_id":event_id,"kickoff_utc":kickoff.isoformat(),
                         "result_first_observed_at_utc":observed.isoformat(),
                         "source_raw_sha256":raw_sha256,
                         "home":home,"away":away,
                         "full_enriched_row":home["all_five_stats_present"] and away["all_five_stats_present"],
                         "prematch_original_feature_equivalence_certified":False,
                         "provider_fixture_crosswalk_certified":False})
        except (ValueError,TypeError,AttributeError,KeyError) as exc:
            blocked.append({"provider_event_id":str(e.get("id")) if isinstance(e,dict) else None,
                            "reason":str(exc)[:140]})
    return {"schema":"MATRIX_ESPN_SIX_LEAGUE_SHA_ENRICHED_HISTORY_V1",
            "status":"HISTORICAL_RESEARCH_ONLY_NOT_PREDICTIONS",
            "original_league_id":str(original_league_id),
            "provider_competition_id":league,
            "observed_at_utc":observed.isoformat(),
            "source_raw_sha256":raw_sha256,
            "verified_source_event_count":len(rows),
            "fully_enriched_event_count":sum(x["full_enriched_row"] for x in rows),
            "rejected_or_not_final_events":blocked,
            "rows":rows,"source_order":["SOFASCORE","FLASHSCORE","ESPN"],
            "future_forecast_must_be_frozen_after_history_observation":True,
            "production_p_matrix_authorized":False,
            "telegram_signal_authorized":False,
            "automatic_wagering":False,"real_money":"BLOCKED"}


def eligible_history(report: dict, *, forecast_frozen_at_utc: str) -> list[dict]:
    if (report.get("schema")!="MATRIX_ESPN_SIX_LEAGUE_SHA_ENRICHED_HISTORY_V1"
        or report.get("production_p_matrix_authorized") is not False
        or report.get("telegram_signal_authorized") is not False):
        raise ValueError("RESEARCH_HISTORY_GOVERNANCE_UNTRUSTED")
    when=dt(forecast_frozen_at_utc)
    return [r for r in report["rows"] if
            dt(r["kickoff_utc"])<dt(r["result_first_observed_at_utc"])<when]


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--capture-report",type=Path,required=True)
    p.add_argument("--league-id",default="239")
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"telegram","notifications","governance","daily_prematch_reports"}:
        raise SystemExit("ESPN_ENRICHMENT_CANNOT_WRITE_PRODUCTION")
    captured=json.loads(args.capture_report.read_text(encoding="utf-8"))
    if (captured.get("schema")!="MATRIX_COLOMBIA_239_PUBLIC_RAW_CAPTURE_V1"
        or args.league_id!="239" or captured.get("telegram_signal_authorized") is not False
        or captured.get("real_money")!="BLOCKED"):
        raise SystemExit("CAPTURE_MANIFEST_MISSING_OR_UNTRUSTED")
    espn=(captured.get("sources") or {}).get("ESPN") or {}
    if espn.get("status")!="AUTHENTIC_RAW_CAPTURE_RESEARCH_ONLY":
        raise SystemExit("ESPN_CAPTURE_NOT_AVAILABLE_NO_FABRICATED_DATA")
    name=espn.get("raw_archive_path")
    if not isinstance(name,str) or Path(name).name!=name:
        raise SystemExit("SOURCE_PATH_MUST_BE_ARCHIVE_SIBLING")
    raw=(args.capture_report.parent/name).read_bytes()
    report=extract(raw,raw_sha256=espn["raw_sha256"],
                   observed_at_utc=espn["observed_at_utc"],
                   original_league_id=args.league_id)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"finalized_research_rows":report["verified_source_event_count"],
                      "enriched_rows":report["fully_enriched_event_count"],
                      "production_authorized":False},sort_keys=True))


if __name__=="__main__":
    main()
