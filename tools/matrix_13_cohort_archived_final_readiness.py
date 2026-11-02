"""Audit archived API-Football receipts for unsettled, pre-kickoff frozen events.

Only reads existing archived network responses. Never calls APIs or alters the
append-only ledgers, forecasts, model parameters, or Telegram. Archived final
receipts are NOT accepted just because a file exists: fixture, kickoff, team
identities, standard FT and full/half score integrity must all match.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.api_football_prospective_api_settlement import _load_ledger

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evidence/api_football/prospective_market_freeze"
REGISTRY = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
PORTFOLIO = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl"
FREEZE = BASE / "freeze.json"
LEDGER = BASE / "settlement_ledger.jsonl"
RAW = BASE / "settlement_raw"
OUT = ROOT / "evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"

PERIOD_MARKETS = {
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY", "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER", "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME", "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
}


def timestamp(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("NON_AWARE_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def inspect_receipt(archived: Path, freeze: dict) -> dict:
    if not archived.is_file():
        return {"code":"MISSING_ARCHIVED_RESPONSE"}
    raw = archived.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError,ValueError):
        return {"code":"ARCHIVED_RESPONSE_NOT_JSON","raw_sha256":sha}
    if not isinstance(data,dict):
        return {"code":"INVALID_PROVIDER_RESPONSE","raw_sha256":sha}
    if data.get("errors") not in (None, [], {}) or data.get("results") != 1:
        return {"code":"PROVIDER_ERROR_OR_NON_EXACT_COUNT","raw_sha256":sha}
    responses=data.get("response")
    if not isinstance(responses,list) or len(responses)!=1:
        return {"code":"PROVIDER_ROW_COUNT_NOT_ONE","raw_sha256":sha}
    item=responses[0]
    fid=str(freeze["fixture_id"])
    fixture=item.get("fixture") or {}
    teams=item.get("teams") or {}
    if str(fixture.get("id"))!=fid:
        return {"code":"FIXTURE_IDENTITY_MISMATCH","raw_sha256":sha}
    if timestamp(fixture.get("date")) != timestamp(freeze["kickoff_utc"]):
        return {"code":"KICKOFF_IDENTITY_MISMATCH","raw_sha256":sha}
    if (str((teams.get("home") or {}).get("id")) != str(freeze["home_team_id"]) or
        str((teams.get("away") or {}).get("id")) != str(freeze["away_team_id"])):
        return {"code":"TEAM_IDENTITY_MISMATCH","raw_sha256":sha}
    status=str((fixture.get("status") or {}).get("short") or "")
    if status!="FT":
        return {"code":"NON_STANDARD_FT_OR_NOT_YET_FINAL","provider_status":status,"raw_sha256":sha}
    score=item.get("score") or {}
    ft=score.get("fulltime") or {}
    half=score.get("halftime") or {}
    hg,ag=ft.get("home"),ft.get("away")
    hh,ah=half.get("home"),half.get("away")
    if any(type(g) is not int or g<0 for g in (hg,ag)):
        return {"code":"FT_SCORE_UNVERIFIED","raw_sha256":sha}
    if (item.get("goals") or {}).get("home")!=hg or (item.get("goals") or {}).get("away")!=ag:
        return {"code":"GOALS_VS_FINAL_SCORE_CONFLICT","raw_sha256":sha}
    halftime_ok=all(type(g) is int and g>=0 for g in (hh,ah)) and hh<=hg and ah<=ag
    return {
      "code":"VERIFIED_ARCHIVED_STANDARD_FT",
      "raw_sha256":sha,
      "halftime_verified":halftime_ok,
      "fulltime_score":[hg,ag],
      "halftime_score":[hh,ah] if halftime_ok else None,
    }


def build(freezes: dict, settled: list[dict], registry: dict, portfolio: list[dict],
          raw_dir: Path) -> dict:
    if (registry.get("status") != "PASS" or registry.get("total_lanes") != 42 or
        (registry.get("protections") or {}).get("real_money") != "BLOCKED"):
        raise ValueError("REGISTRY_NOT_VALID")
    freeze_rows=freezes.get("rows")
    if not isinstance(freeze_rows,list):
        raise ValueError("NO_FREEZE_ROWS")
    seen=set()
    for row in freeze_rows:
        fid=str(row.get("fixture_id") or "")
        if not fid or fid in seen:
            raise ValueError("DUPLICATED_OR_MISSING_FREEZE_FIXTURE")
        seen.add(fid)
    previous={str(x["fixture_id"]) for x in settled}
    lanes={k for k,v in registry["lanes"].items() if v["prospective_unique_count"]>=600}
    if len(lanes)!=13:
        raise ValueError("EXPECTED_EXACTLY_13_GATE600_MARKETS")
    target_to_fixtures={k:set() for k in lanes}
    for row in portfolio:
        k=row.get("market_lane")
        if k in lanes and row.get("prospective_admitted") is True:
            target_to_fixtures[k].add(str(row.get("fixture_id") or row.get("event_id") or ""))
    target_ids=set().union(*target_to_fixtures.values())
    sources={str(row["fixture_id"]):row for row in freeze_rows}
    relevant={fid for fid in target_ids if fid and fid not in previous}
    data={}
    for fid in relevant:
        src=sources.get(fid)
        if src is None:
            data[fid]={"code":"MISSING_CANONICAL_PREMATCH_FREEZE"}
            continue
        try:
            freeze_time=timestamp(src["freeze_at_utc"])
            start=timestamp(src["kickoff_utc"])
            if freeze_time>=start:
                data[fid]={"code":"NOT_STRICTLY_PREMATCH_FROZEN"}
                continue
            data[fid]=inspect_receipt(raw_dir / f"fixture_{fid}.bin",src)
        except (ValueError,TypeError,KeyError):
            data[fid]={"code":"UNTRUSTED_FREEZE_OR_ARCHIVED_RECEIPT"}
    triage_queue=[]
    for fid in sorted(relevant):
        src=sources.get(fid) or {}
        row=data.get(fid) or {"code":"UNKNOWN"}
        triage_queue.append({
          "fixture_id":fid,
          "kickoff_utc":src.get("kickoff_utc"),
          "home_team_id":str(src.get("home_team_id")) if src.get("home_team_id") is not None else None,
          "away_team_id":str(src.get("away_team_id")) if src.get("away_team_id") is not None else None,
          "freeze_at_utc":src.get("freeze_at_utc"),
          "archived_source_status":row.get("code"),
          "archived_provider_status":row.get("provider_status"),
          "archived_response_sha256":row.get("raw_sha256"),
          "affected_gate600_lanes":sorted(k for k,ids in target_to_fixtures.items() if fid in ids),
          "recovery_policy":"REQUIRE_AUTHENTIC_STANDARD_FT_AND_EXACT_EVENT_TEAM_KICKOFF_MATCH_BEFORE_SETTLEMENT",
          "safe_to_settle_from_present_archive":row.get("code")=="VERIFIED_ARCHIVED_STANDARD_FT",
          "prospective_freeze_not_to_be_rewritten":True,
        })
    lane_rows=[]
    for k in sorted(lanes):
        target=target_to_fixtures[k]
        missing=target-previous
        reasons=Counter(data.get(fid,{}).get("code","UNKNOWN") for fid in missing)
        final=sum(1 for fid in missing if data.get(fid,{}).get("code")=="VERIFIED_ARCHIVED_STANDARD_FT")
        half=sum(1 for fid in missing if data.get(fid,{}).get("halftime_verified") is True)
        lane_rows.append({
          "market_key":k,
          "prospective_unique_count":registry["lanes"][k]["prospective_unique_count"],
          "missing_settlement_event_count":len(missing),
          "recoverable_archived_standard_ft_events":final,
          "recoverable_archived_halftime_events":half,
          "reasons":dict(sorted(reasons.items())),
          "historical_backfill_applied":False,
          "settlements_appended":0,
          "production_authorized":False,
        })
    return {
      "schema":"MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":"PASS_READ_ONLY_NO_LEDGER_WRITES",
      "source_freeze_count":len(freeze_rows),
      "verified_settlement_ledger_rows":len(settled),
      "distinct_missing_market_fixture_ids":len(relevant),
      "target_market_count":len(lane_rows),
      "unsettled_fixture_triage":triage_queue,
      "unsettled_fixture_triage_count":len(triage_queue),
      "lanes":lane_rows,
      "protections":{
        "read_only":True,
        "no_api_calls":True,
        "no_post_start_prediction_backfill":True,
        "no_fake_settlements":True,
        "no_auto_provider_retry_or_paid_api_calls":True,
        "recoverable_from_archives_requires_verified_receipt":True,
        "ft_only":True,
        "archive_fixture_kickoff_team_identity_required":True,
        "no_telegram_signal_promotion":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      },
    }


def main() -> None:
    freezes=json.loads(FREEZE.read_text(encoding="utf-8"))
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    portfolio=[json.loads(x) for x in PORTFOLIO.read_text(encoding="utf-8").splitlines() if x.strip()]
    result=build(freezes,_load_ledger(LEDGER),registry,portfolio,RAW)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"source_settled":result["verified_settlement_ledger_rows"],
        "lanes":[{"market":x["market_key"],"missing":x["missing_settlement_event_count"],
                  "archived_final":x["recoverable_archived_standard_ft_events"],
                  "archived_halftime":x["recoverable_archived_halftime_events"]} for x in result["lanes"]]},sort_keys=True))


if __name__=="__main__":
    main()
