from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools.api_football_extended_market_historical_bootstrap import _player_rows,_request,_stat_map

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20
LEAGUES=("72","252")
TARGET_SEASON=2025
MAX_FIXTURES_DEFAULT=45


def _utc(v:object)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _current_team_ids()->set[str]:
    ids=set()
    for p in (
        Path("evidence/api_football/history/raw/league_72_season_2026.bin"),
        Path("evidence/api_football/history/raw/league_252_season_2026.bin"),
    ):
        payload=json.loads(p.read_bytes().decode("utf-8"))
        for row in payload.get("response") or []:
            teams=row.get("teams") if isinstance(row,Mapping) else None
            if not isinstance(teams,Mapping):
                continue
            for side in ("home","away"):
                team=teams.get(side)
                if isinstance(team,Mapping) and team.get("id") is not None:
                    ids.add(str(team["id"]))
    return ids


def _fixture_list(client:Any,key:str,league:str):
    r=client.get(
        BASE_URL+"/fixtures",
        headers={"x-apisports-key":key},
        params={"league":league,"season":TARGET_SEASON},
        timeout=TIMEOUT,
    )
    body=bytes(r.content)
    payload=r.json()
    errors=payload.get("errors") if isinstance(payload,Mapping) else None
    if not (200 <= int(r.status_code) < 300 and errors in ({},[],None)):
        raise ValueError(f"FIXTURE_LIST_PROVIDER_ERROR:{league}:{r.status_code}:{errors}")
    return payload,body,r.headers.get("x-ratelimit-requests-remaining")


def _parse_candidates(payload:Mapping[str,Any],league:str,current_teams:set[str])->list[dict[str,Any]]:
    out=[]
    for raw in payload.get("response") or []:
        if not isinstance(raw,Mapping):
            continue
        fixture=raw.get("fixture"); teams=raw.get("teams"); league_obj=raw.get("league")
        if not isinstance(fixture,Mapping) or not isinstance(teams,Mapping) or not isinstance(league_obj,Mapping):
            continue
        status=fixture.get("status")
        if not isinstance(status,Mapping) or str(status.get("short") or "").upper() not in {"FT","AET","PEN"}:
            continue
        home=teams.get("home"); away=teams.get("away")
        if not isinstance(home,Mapping) or not isinstance(away,Mapping):
            continue
        try:
            fid=str(int(fixture["id"])); hid=str(int(home["id"])); aid=str(int(away["id"]))
            kickoff=_utc(fixture["date"])
        except (KeyError,TypeError,ValueError):
            continue
        overlap=int(hid in current_teams)+int(aid in current_teams)
        if overlap==0:
            continue
        out.append({
            "fixture_id":fid,
            "kickoff_utc":kickoff.isoformat(),
            "league_id":league,
            "season":TARGET_SEASON,
            "home_team_id":hid,"away_team_id":aid,
            "home_team_name":str(home.get("name") or ""),
            "away_team_name":str(away.get("name") or ""),
            "current_2026_team_overlap":overlap,
        })
    out.sort(key=lambda r:(-r["current_2026_team_overlap"],-_utc(r["kickoff_utc"]).timestamp(),int(r["fixture_id"])))
    return out


def _select(by_league:dict[str,list[dict[str,Any]]],limit:int)->list[dict[str,Any]]:
    chosen=[]
    positions={k:0 for k in LEAGUES}
    while len(chosen)<limit:
        progressed=False
        for league in LEAGUES:
            pos=positions[league]
            rows=by_league.get(league,[])
            if pos<len(rows) and len(chosen)<limit:
                chosen.append(rows[pos])
                positions[league]+=1
                progressed=True
        if not progressed:
            break
    chosen.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
    return chosen


def run(api_key:str,out_dir:Path,max_fixtures:int=MAX_FIXTURES_DEFAULT,daily_reserve:int=5000,session:Any|None=None)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    if max_fixtures<1 or max_fixtures>50:
        raise ValueError("MAX_FIXTURES_OUT_OF_POLICY")
    client=session or requests.Session()
    out_dir.mkdir(parents=True,exist_ok=True)
    raw_dir=out_dir/"raw"; raw_dir.mkdir(parents=True,exist_ok=True)
    current_teams=_current_team_ids()
    by_league={}
    calls=0
    remaining=None
    fixture_list_meta=[]

    for league in LEAGUES:
        payload,body,remaining=_fixture_list(client,key,league)
        calls+=1
        (raw_dir/f"league_{league}_season_{TARGET_SEASON}_fixtures.bin").write_bytes(body)
        candidates=_parse_candidates(payload,league,current_teams)
        by_league[league]=candidates
        fixture_list_meta.append({
            "league_id":league,
            "candidate_count":len(candidates),
            "raw_sha256":hashlib.sha256(body).hexdigest(),
        })

    selected=_select(by_league,max_fixtures)
    normalized=[]
    captures=[]
    stopped_reason=None

    for src in selected:
        if remaining is not None and int(remaining)<=daily_reserve:
            stopped_reason="DAILY_RESERVE_REACHED"
            break
        fid=src["fixture_id"]
        stat,sbody,sok,srem,sstatus=_request(client,key,"/fixtures/statistics",fid)
        calls+=1; remaining=srem
        (raw_dir/f"fixture_{fid}_statistics.bin").write_bytes(sbody)
        stat_sha=hashlib.sha256(sbody).hexdigest()
        team_stats=_stat_map(stat) if sok else {}
        if not team_stats:
            captures.append({"fixture_id":fid,"status":"NO_TEAM_STATISTICS","statistics_sha256":stat_sha})
            continue
        time.sleep(0.15)
        if remaining is not None and int(remaining)<=daily_reserve:
            stopped_reason="DAILY_RESERVE_REACHED"
            break
        players,pbody,pok,prem,pstatus=_request(client,key,"/fixtures/players",fid)
        calls+=1; remaining=prem
        (raw_dir/f"fixture_{fid}_players.bin").write_bytes(pbody)
        player_sha=hashlib.sha256(pbody).hexdigest()
        player_rows=_player_rows(players) if pok else []
        normalized.append({
            **src,
            "team_statistics":team_stats,
            "player_statistics":player_rows,
            "statistics_sha256":stat_sha,
            "players_sha256":player_sha,
            "development_role":"HISTORICAL_PRIOR_SEASON_WARMUP",
            "protected_holdout_member":False,
            "prospective_calibration_member":False,
        })
        captures.append({
            "fixture_id":fid,"status":"CAPTURED",
            "team_statistics_present":True,
            "player_statistics_present":bool(player_rows),
            "player_row_count":len(player_rows),
            "statistics_sha256":stat_sha,"players_sha256":player_sha,
        })
        time.sleep(0.15)

    dataset=out_dir/"normalized_dataset.jsonl"
    dataset.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in normalized),encoding="utf-8")
    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_PRIOR_SEASON_WARMUP_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_provider":"api_football",
        "source_season":TARGET_SEASON,
        "source_leagues":list(LEAGUES),
        "current_2026_team_count":len(current_teams),
        "fixture_lists":fixture_list_meta,
        "selected_fixture_count":len(selected),
        "captured_fixture_count":len(normalized),
        "team_statistics_covered_count":sum(1 for x in captures if x.get("team_statistics_present")),
        "player_statistics_covered_count":sum(1 for x in captures if x.get("player_statistics_present")),
        "network_calls":calls,
        "daily_reserve_policy":daily_reserve,
        "last_daily_remaining":remaining,
        "stopped_reason":stopped_reason,
        "dataset_path":str(dataset),
        "dataset_sha256":hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "captures":captures,
        "all_rows_strictly_before_2026":all(_utc(r["kickoff_utc"]).year<=2025 for r in normalized),
        "protected_holdout_intersection_count":0,
        "prospective_intersection_count":0,
        "feature_usage_policy":"STRICTLY_PRIOR_MATCHES_ONLY",
        "odds_used_to_generate_probability":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def main():
    result=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path("evidence/api_football/market_expansion/historical_prior_season"),
        max_fixtures=int(os.environ.get("MATRIX_EXTENDED_PRIOR_SEASON_MAX_FIXTURES","45")),
        daily_reserve=int(os.environ.get("MATRIX_API_FOOTBALL_DAILY_RESERVE","5000")),
    )
    print(json.dumps({
        "status":result["status"],
        "selected_fixture_count":result["selected_fixture_count"],
        "captured_fixture_count":result["captured_fixture_count"],
        "team_statistics_covered_count":result["team_statistics_covered_count"],
        "player_statistics_covered_count":result["player_statistics_covered_count"],
        "network_calls":result["network_calls"],
        "last_daily_remaining":result["last_daily_remaining"],
        "stopped_reason":result["stopped_reason"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
