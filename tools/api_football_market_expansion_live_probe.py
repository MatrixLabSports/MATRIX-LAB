from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TARGET_BETS={220:"Shots. Away Total",221:"Shots. Home Total"}
POLICY_BOOKS={"betano","bwin","pinnacle"}
TIMEOUT=20.0

def _utc(v: object) -> datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)

def _future_events(now: datetime, minutes: int, limit: int) -> list[dict[str,Any]]:
    by_id: dict[str,dict[str,Any]]={}
    for p in sorted(Path("evidence/api_football/prospective_daily").glob("*/*/fixtures/future_fixture_registry.json")):
        try:
            obj=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            continue
        captured=str(obj.get("captured_at_utc") or "")
        for e in obj.get("events") or []:
            if not isinstance(e,Mapping):
                continue
            fid=str(e.get("provider_fixture_id") or "")
            start=e.get("event_start_utc")
            if not fid or not start:
                continue
            kickoff=_utc(start)
            if not (now < kickoff <= now+timedelta(minutes=minutes)):
                continue
            row=dict(e); row["_captured"]=captured
            if fid not in by_id or str(by_id[fid].get("_captured") or "") < captured:
                by_id[fid]=row
    return sorted(by_id.values(),key=lambda x:(_utc(x["event_start_utc"]),int(x["provider_fixture_id"])))[:limit]

def _extract_odds(payload: Mapping[str,Any]) -> list[dict[str,Any]]:
    out=[]
    for fixture in payload.get("response") or []:
        if not isinstance(fixture,Mapping):
            continue
        for book in fixture.get("bookmakers") or []:
            if not isinstance(book,Mapping):
                continue
            name=str(book.get("name") or "")
            for bet in book.get("bets") or []:
                if not isinstance(bet,Mapping):
                    continue
                try: bid=int(bet.get("id"))
                except (TypeError,ValueError): continue
                if bid not in TARGET_BETS:
                    continue
                out.append({
                    "bookmaker_id":book.get("id"),
                    "bookmaker_name":name,
                    "policy_reference_bookmaker":name.strip().casefold() in POLICY_BOOKS,
                    "bet_id":bid,
                    "bet_name":bet.get("name"),
                    "values":[{
                        "value":v.get("value"),"odd":v.get("odd"),"handicap":v.get("handicap"),
                        "main":v.get("main"),"suspended":v.get("suspended")
                    } for v in (bet.get("values") or []) if isinstance(v,Mapping)]
                })
    return out

def _extract_lineups(payload: Mapping[str,Any]) -> dict[str,Any]:
    teams=[]
    for team_row in payload.get("response") or []:
        if not isinstance(team_row,Mapping):
            continue
        team=team_row.get("team") if isinstance(team_row.get("team"),Mapping) else {}
        starters=[]
        subs=[]
        for item in team_row.get("startXI") or []:
            p=item.get("player") if isinstance(item,Mapping) and isinstance(item.get("player"),Mapping) else {}
            if p.get("id"):
                starters.append({"player_id":str(p.get("id")),"player_name":p.get("name"),"role":"STARTER"})
        for item in team_row.get("substitutes") or []:
            p=item.get("player") if isinstance(item,Mapping) and isinstance(item.get("player"),Mapping) else {}
            if p.get("id"):
                subs.append({"player_id":str(p.get("id")),"player_name":p.get("name"),"role":"SUBSTITUTE"})
        teams.append({
            "team_id":str(team.get("id") or ""),"team_name":team.get("name"),
            "starter_count":len(starters),"substitute_count":len(subs),
            "players":starters+subs
        })
    return {"team_count":len(teams),"player_count":sum(len(t["players"]) for t in teams),"teams":teams}

def run(api_key: str, out_root: Path) -> dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    run_id=now.strftime("%Y%m%dT%H%M%SZ")
    run_dir=out_root/"runs"/run_id
    raw=run_dir/"raw"; raw.mkdir(parents=True,exist_ok=True)
    session=requests.Session()

    odds_events=_future_events(now,24*60,16)
    lineup_events=_future_events(now,4*60,16)
    odds_rows=[]
    for e in odds_events:
        fid=str(e["provider_fixture_id"])
        resp=session.get(BASE_URL+"/odds",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        body=bytes(resp.content); (raw/f"fixture_{fid}_odds.bin").write_bytes(body)
        try: payload=resp.json()
        except ValueError: payload={}
        hits=_extract_odds(payload) if 200 <= int(resp.status_code)<300 else []
        odds_rows.append({
            "fixture_id":fid,"kickoff_utc":e.get("event_start_utc"),
            "home_team":e.get("home_team"),"away_team":e.get("away_team"),
            "http_status":int(resp.status_code),"hits":hits,
            "raw_sha256":hashlib.sha256(body).hexdigest()
        })

    lineup_rows=[]
    for e in lineup_events:
        fid=str(e["provider_fixture_id"])
        resp=session.get(BASE_URL+"/fixtures/lineups",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        body=bytes(resp.content); (raw/f"fixture_{fid}_lineups.bin").write_bytes(body)
        try: payload=resp.json()
        except ValueError: payload={}
        parsed=_extract_lineups(payload) if 200 <= int(resp.status_code)<300 else {"team_count":0,"player_count":0,"teams":[]}
        lineup_rows.append({
            "fixture_id":fid,"kickoff_utc":e.get("event_start_utc"),
            "home_team":e.get("home_team"),"away_team":e.get("away_team"),
            "http_status":int(resp.status_code),"lineup":parsed,
            "raw_sha256":hashlib.sha256(body).hexdigest()
        })

    odds_hits=[h for r in odds_rows for h in r["hits"]]
    policy_hits=[h for h in odds_hits if h["policy_reference_bookmaker"]]
    lineup_observed=[r for r in lineup_rows if r["lineup"]["team_count"]>=2 and r["lineup"]["player_count"]>0]

    payload={
        "schema":"MATRIX_FOOTBALL_MARKET_EXPANSION_LIVE_PROBE_V1",
        "run_id":run_id,"observed_at_utc":now.isoformat(),
        "provider":"api_football",
        "network_calls":len(odds_rows)+len(lineup_rows),
        "team_total_shots":{
            "target_bets":TARGET_BETS,
            "candidate_count":len(odds_rows),
            "canonical_live_hit_count":len(odds_hits),
            "policy_reference_live_hit_count":len(policy_hits),
            "bookmaker_scope":"HOME_OR_AWAY_TEAM_TOTAL_SHOTS",
            "current_historical_model_scope":"COMBINED_MATCH_TOTAL_SHOTS",
            "scope_alignment_certified":False,
            "prospective_freeze_allowed":False,
            "blocker":"CURRENT_COMBINED_MODEL_SCOPE_DOES_NOT_MATCH_HOME_AWAY_BOOKMAKER_TARGETS",
            "rows":odds_rows
        },
        "player_shots":{
            "candidate_count":len(lineup_rows),
            "prematch_lineup_observed_count":len(lineup_observed),
            "prematch_lineup_structure_observed":bool(lineup_observed),
            "provider_role_mapping":{"startXI":"STARTER","substitutes":"SUBSTITUTE"},
            "cross_source_role_equivalence_certified":False,
            "expected_minutes_pit_prospective_certified":False,
            "prospective_freeze_allowed":False,
            "blocker":"REQUIRES_CROSS_SOURCE_ROLE_EQUIVALENCE_AND_EXPECTED_MINUTES_PROSPECTIVE_CERTIFICATION",
            "rows":lineup_rows
        },
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS"
    }
    manifest=run_dir/"manifest.json"
    manifest.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    out_root.mkdir(parents=True,exist_ok=True)
    pointer={
        "schema":"MATRIX_FOOTBALL_MARKET_EXPANSION_LIVE_PROBE_POINTER_V1",
        "run_id":run_id,
        "manifest_path":str(manifest),
        "manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "network_calls":payload["network_calls"],
        "team_total_shots_live_hit_count":len(odds_hits),
        "player_shots_lineup_observed_count":len(lineup_observed),
        "team_total_shots_prospective_freeze_allowed":False,
        "player_shots_prospective_freeze_allowed":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS"
    }
    (out_root/"last_run.json").write_text(json.dumps(pointer,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return pointer

def main() -> None:
    result=run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/market_expansion/live_probe"))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
