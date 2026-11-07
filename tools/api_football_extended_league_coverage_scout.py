from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20
PER_LEAGUE=3
EXCLUDED_LEAGUES={"72","252"}

DATASETS=(
    Path("evidence/api_football/market_expansion/historical_bootstrap/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3/normalized_dataset.jsonl"),
)

def _read_jsonl_ids(path:Path)->set[str]:
    out=set()
    if not path.exists(): return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw)
            if row.get("fixture_id") is not None:
                out.add(str(row["fixture_id"]))
    return out

def _load_candidates()->dict[str,list[dict[str,Any]]]:
    obj=json.loads(Path("evidence/api_football/model_validation/retrospective_predictions_chunks/chunk_0001.json").read_text(encoding="utf-8"))
    rows=obj.get("rows") if isinstance(obj,Mapping) else obj
    protected=json.loads(Path("evidence/api_football/challenger/final_holdout_seal.json").read_text(encoding="utf-8"))
    protected_ids={str(x["fixture_id"]) for x in protected["rows"]}
    queried=set()
    for p in DATASETS: queried |= _read_jsonl_ids(p)
    by=defaultdict(list)
    for r in rows:
        fid=str(r.get("fixture_id") or "")
        league=str(r.get("league_id") or "")
        if not fid or not league or league in EXCLUDED_LEAGUES or fid in protected_ids or fid in queried:
            continue
        by[league].append(dict(r))
    for league in by:
        by[league].sort(key=lambda x:(str(x.get("kickoff_utc") or ""),int(x["fixture_id"])),reverse=True)
    return by

def _get(client,key,endpoint,fid):
    resp=client.get(BASE_URL+endpoint,headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
    body=bytes(resp.content)
    payload=resp.json()
    errors=payload.get("errors") if isinstance(payload,Mapping) else None
    rows=payload.get("response") if isinstance(payload,Mapping) else None
    ok=200 <= int(resp.status_code) < 300 and errors in ({},[],None) and isinstance(rows,list)
    return payload,body,ok,resp.headers.get("x-ratelimit-requests-remaining")

def _team_fields(payload):
    response=payload.get("response") if isinstance(payload,Mapping) else None
    if not isinstance(response,list): return False
    types=set()
    for team in response:
        if not isinstance(team,Mapping): continue
        for item in team.get("statistics") or []:
            if isinstance(item,Mapping):
                types.add(str(item.get("type") or ""))
    required={"Corner Kicks","Shots on Goal","Total Shots","Fouls","Yellow Cards"}
    return required.issubset(types)

def _player_fields(payload):
    response=payload.get("response") if isinstance(payload,Mapping) else None
    if not isinstance(response,list): return False
    for team in response:
        if isinstance(team,Mapping) and isinstance(team.get("players"),list) and team.get("players"):
            return True
    return False

def run(api_key:str,out_dir:Path,session:Any|None=None,per_league:int=PER_LEAGUE)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    client=session or requests.Session()
    out_dir.mkdir(parents=True,exist_ok=True)
    by=_load_candidates()
    league_results={}
    calls=0
    remaining=None

    for league in sorted(by):
        samples=by[league][:per_league]
        records=[]
        for row in samples:
            fid=str(row["fixture_id"])
            stat,sbody,sok,remaining=_get(client,key,"/fixtures/statistics",fid)
            calls+=1
            team_ok=bool(sok and _team_fields(stat))
            player_ok=False
            psha=None
            if team_ok:
                players,pbody,pok,remaining=_get(client,key,"/fixtures/players",fid)
                calls+=1
                player_ok=bool(pok and _player_fields(players))
                psha=hashlib.sha256(pbody).hexdigest()
            records.append({
                "fixture_id":fid,
                "kickoff_utc":row.get("kickoff_utc"),
                "team_extended_fields":team_ok,
                "player_statistics":player_ok,
                "statistics_sha256":hashlib.sha256(sbody).hexdigest(),
                "players_sha256":psha,
            })
        team_hits=sum(int(x["team_extended_fields"]) for x in records)
        player_hits=sum(int(x["player_statistics"]) for x in records)
        league_results[league]={
            "sampled":len(records),
            "team_hits":team_hits,
            "player_hits":player_hits,
            "qualified_team":team_hits>0,
            "qualified_player":player_hits>0,
            "records":records,
        }

    qualified_team=sorted(k for k,v in league_results.items() if v["qualified_team"])
    qualified_player=sorted(k for k,v in league_results.items() if v["qualified_player"])
    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_LEAGUE_COVERAGE_SCOUT_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_football",
        "per_league_sample":per_league,
        "excluded_known_statsrich_leagues":sorted(EXCLUDED_LEAGUES),
        "league_count_scouted":len(league_results),
        "network_calls":calls,
        "last_daily_remaining":remaining,
        "qualified_team_leagues":qualified_team,
        "qualified_player_leagues":qualified_player,
        "league_results":league_results,
        "purpose":"Coverage discovery only; no model fitting or validation metrics.",
        "metrics_opened":False,
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest

def main():
    r=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path("evidence/api_football/market_expansion/league_coverage_scout"),
        per_league=int(os.environ.get("MATRIX_EXTENDED_SCOUT_PER_LEAGUE","3")),
    )
    print(json.dumps({
        "status":r["status"],
        "league_count_scouted":r["league_count_scouted"],
        "network_calls":r["network_calls"],
        "qualified_team_leagues":r["qualified_team_leagues"],
        "qualified_player_leagues":r["qualified_player_leagues"],
        "last_daily_remaining":r["last_daily_remaining"],
    },sort_keys=True))

if __name__=="__main__":
    main()
