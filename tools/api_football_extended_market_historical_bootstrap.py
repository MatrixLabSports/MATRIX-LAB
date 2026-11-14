from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT_SECONDS=20.0
DEFAULT_MAX_FIXTURES=100
DEFAULT_DAILY_RESERVE=5000
SLEEP_SECONDS=0.25

def _utc(value: object) -> datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)

def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _prediction_rows(path: Path) -> list[dict[str,Any]]:
    obj=_load_json(path)
    rows=obj.get("rows") if isinstance(obj,Mapping) else obj
    if not isinstance(rows,list):
        raise ValueError("RETROSPECTIVE_ROWS_MISSING")
    return [dict(r) for r in rows if isinstance(r,Mapping)]

def _protected_ids(seal_path: Path) -> tuple[set[str],datetime]:
    obj=_load_json(seal_path)
    rows=obj.get("rows")
    if not isinstance(rows,list) or not rows:
        raise ValueError("FINAL_HOLDOUT_ROWS_MISSING")
    ids={str(r.get("fixture_id")) for r in rows if isinstance(r,Mapping) and r.get("fixture_id") is not None}
    starts=[_utc(r["kickoff_utc"]) for r in rows if isinstance(r,Mapping) and r.get("kickoff_utc")]
    return ids,min(starts)

def _prospective_ids(path: Path) -> set[str]:
    ids=set()
    if not path.exists():
        return ids
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw)
            if row.get("fixture_id") is not None:
                ids.add(str(row["fixture_id"]))
    return ids

def select_development_candidates(
    rows:list[dict[str,Any]],
    protected_ids:set[str],
    prospective_ids:set[str],
    cutoff:datetime,
    limit:int,
    allowed_leagues:set[str]|None=None,
    extra_excluded_ids:set[str]|None=None,
)->list[dict[str,Any]]:
    eligible=[]
    extra_excluded_ids=extra_excluded_ids or set()
    for r in rows:
        fid=str(r.get("fixture_id") or "").strip()
        kickoff=r.get("kickoff_utc")
        league=str(r.get("league_id") or "")
        if not fid or not kickoff or fid in protected_ids or fid in prospective_ids or fid in extra_excluded_ids:
            continue
        if allowed_leagues is not None and league not in allowed_leagues:
            continue
        if _utc(kickoff) >= cutoff:
            continue
        eligible.append(r)
    eligible.sort(key=lambda r:(str(r.get("league_id") or ""),str(r.get("kickoff_utc") or ""),str(r.get("fixture_id") or "")))
    by_league=defaultdict(list)
    for r in eligible:
        by_league[str(r.get("league_id") or "UNKNOWN")].append(r)
    selected=[]
    league_keys=sorted(by_league)
    idx=0
    while len(selected)<limit and league_keys:
        league=league_keys[idx % len(league_keys)]
        bucket=by_league[league]
        if bucket:
            selected.append(bucket.pop())
        if not bucket:
            league_keys.remove(league)
            if not league_keys:
                break
            idx=idx % len(league_keys)
        else:
            idx+=1
    selected.sort(key=lambda r:(str(r.get("kickoff_utc") or ""),str(r.get("fixture_id") or "")))
    return selected

def _stat_map(payload:Mapping[str,Any])->dict[str,dict[str,Any]]:
    out={}
    for team in payload.get("response") or []:
        if not isinstance(team,Mapping): continue
        team_obj=team.get("team")
        stats=team.get("statistics")
        if not isinstance(team_obj,Mapping) or not isinstance(stats,list): continue
        tid=str(team_obj.get("id") or "")
        if not tid: continue
        m={}
        for item in stats:
            if isinstance(item,Mapping):
                m[str(item.get("type") or "").strip()]=item.get("value")
        out[tid]={"team_name":team_obj.get("name"),"statistics":m}
    return out

def _player_rows(payload:Mapping[str,Any])->list[dict[str,Any]]:
    rows=[]
    for team in payload.get("response") or []:
        if not isinstance(team,Mapping): continue
        team_obj=team.get("team")
        if not isinstance(team_obj,Mapping): continue
        tid=str(team_obj.get("id") or "")
        for player in team.get("players") or []:
            if not isinstance(player,Mapping): continue
            pobj=player.get("player")
            if not isinstance(pobj,Mapping): continue
            for s in player.get("statistics") or []:
                if not isinstance(s,Mapping): continue
                rows.append({
                    "team_id":tid,
                    "team_name":team_obj.get("name"),
                    "player_id":str(pobj.get("id") or ""),
                    "player_name":pobj.get("name"),
                    "minutes":(s.get("games") or {}).get("minutes") if isinstance(s.get("games"),Mapping) else None,
                    "shots_total":(s.get("shots") or {}).get("total") if isinstance(s.get("shots"),Mapping) else None,
                    "shots_on_target":(s.get("shots") or {}).get("on") if isinstance(s.get("shots"),Mapping) else None,
                    "assists":(s.get("goals") or {}).get("assists") if isinstance(s.get("goals"),Mapping) else None,
                    "saves":(s.get("goals") or {}).get("saves") if isinstance(s.get("goals"),Mapping) else None,
                    "passes_total":(s.get("passes") or {}).get("total") if isinstance(s.get("passes"),Mapping) else None,
                    "tackles_total":(s.get("tackles") or {}).get("total") if isinstance(s.get("tackles"),Mapping) else None,
                    "fouls_committed":(s.get("fouls") or {}).get("committed") if isinstance(s.get("fouls"),Mapping) else None,
                })
    return rows

def _request(client:Any,key:str,endpoint:str,fid:str):
    response=client.get(
        BASE_URL+endpoint,
        headers={"x-apisports-key":key},
        params={"fixture":fid},
        timeout=TIMEOUT_SECONDS,
    )
    body=bytes(response.content)
    payload=response.json()
    errors=payload.get("errors") if isinstance(payload,Mapping) else None
    ok=200 <= int(response.status_code) < 300 and errors in ({},[],None)
    remaining=response.headers.get("x-ratelimit-requests-remaining")
    return payload,body,ok,remaining,int(response.status_code)

def run(api_key:str,out_dir:Path,max_fixtures:int=DEFAULT_MAX_FIXTURES,daily_reserve:int=DEFAULT_DAILY_RESERVE,session:Any|None=None,allowed_leagues:set[str]|None=None,exclude_dataset_paths:tuple[Path,...]=())->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    if max_fixtures<1 or max_fixtures>200:
        raise ValueError("MAX_FIXTURES_OUT_OF_POLICY")

    rows=_prediction_rows(Path("evidence/api_football/model_validation/retrospective_predictions_chunks/chunk_0001.json"))
    protected,cutoff=_protected_ids(Path("evidence/api_football/challenger/final_holdout_seal.json"))
    prospective=_prospective_ids(Path("evidence/api_football/prospective_calibration/ledger.jsonl"))
    prior_ids=set()
    for prev_path in exclude_dataset_paths:
        if not prev_path.exists():
            continue
        for raw in prev_path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row=json.loads(raw)
                if row.get("fixture_id") is not None:
                    prior_ids.add(str(row["fixture_id"]))
    selected=select_development_candidates(
        rows,protected,prospective,cutoff,max_fixtures,
        allowed_leagues=allowed_leagues,
        extra_excluded_ids=prior_ids,
    )

    out_dir.mkdir(parents=True,exist_ok=True)
    raw_dir=out_dir/"raw"; raw_dir.mkdir(parents=True,exist_ok=True)
    client=session or requests.Session()
    normalized=[]
    captures=[]
    network_calls=0
    last_remaining=None
    stopped_reason=None

    for src in selected:
        if last_remaining is not None and int(last_remaining) <= daily_reserve:
            stopped_reason="DAILY_RESERVE_REACHED"
            break
        fid=str(src["fixture_id"])

        stat,body,ok,rem,status=_request(client,key,"/fixtures/statistics",fid)
        network_calls+=1
        (raw_dir/f"fixture_{fid}_statistics.bin").write_bytes(body)
        stat_sha=hashlib.sha256(body).hexdigest()
        last_remaining=rem
        if not ok:
            captures.append({"fixture_id":fid,"status":"STATISTICS_PROVIDER_BLOCKED","http_status":status,"statistics_sha256":stat_sha})
            continue
        time.sleep(SLEEP_SECONDS)

        players,pbody,pok,prem,pstatus=_request(client,key,"/fixtures/players",fid)
        network_calls+=1
        (raw_dir/f"fixture_{fid}_players.bin").write_bytes(pbody)
        player_sha=hashlib.sha256(pbody).hexdigest()
        last_remaining=prem
        if not pok:
            captures.append({"fixture_id":fid,"status":"PLAYERS_PROVIDER_BLOCKED","http_status":pstatus,"statistics_sha256":stat_sha,"players_sha256":player_sha})
            continue

        teams=_stat_map(stat)
        player_rows=_player_rows(players)
        has_team=bool(teams)
        has_players=bool(player_rows)
        normalized.append({
            "fixture_id":fid,
            "kickoff_utc":src.get("kickoff_utc"),
            "league_id":str(src.get("league_id") or ""),
            "season":src.get("season"),
            "team_statistics":teams,
            "player_statistics":player_rows,
            "statistics_sha256":stat_sha,
            "players_sha256":player_sha,
            "development_role":"HISTORICAL_DEVELOPMENT_ONLY",
            "protected_holdout_member":False,
            "prospective_calibration_member":False,
        })
        captures.append({
            "fixture_id":fid,
            "status":"CAPTURED",
            "team_statistics_present":has_team,
            "player_statistics_present":has_players,
            "player_row_count":len(player_rows),
            "statistics_sha256":stat_sha,
            "players_sha256":player_sha,
        })
        time.sleep(SLEEP_SECONDS)

    dataset_path=out_dir/"normalized_dataset.jsonl"
    dataset_path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in normalized),encoding="utf-8")

    team_covered=sum(1 for r in captures if r.get("team_statistics_present"))
    player_covered=sum(1 for r in captures if r.get("player_statistics_present"))
    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_MARKET_HISTORICAL_BOOTSTRAP_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_provider":"api_football",
        "retrospective_source_rows":len(rows),
        "protected_final_holdout_count":len(protected),
        "prospective_exclusion_count":len(prospective),
        "prior_dataset_exclusion_count":len(prior_ids),
        "allowed_leagues":sorted(allowed_leagues) if allowed_leagues is not None else None,
        "development_cutoff_utc":cutoff.isoformat(),
        "selected_fixture_count":len(selected),
        "captured_fixture_count":len(normalized),
        "team_statistics_covered_count":team_covered,
        "player_statistics_covered_count":player_covered,
        "network_calls":network_calls,
        "daily_reserve_policy":daily_reserve,
        "last_daily_remaining":last_remaining,
        "stopped_reason":stopped_reason,
        "dataset_path":str(dataset_path),
        "dataset_sha256":hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "captures":captures,
        "protected_holdout_intersection_count":0,
        "prospective_intersection_count":0,
        "outcomes_used_for_prospective_claims":False,
        "odds_used_to_generate_probability":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest

def main()->None:
    raw_leagues=os.environ.get("MATRIX_EXTENDED_BOOTSTRAP_ALLOWED_LEAGUES","").strip()
    allowed_leagues={x.strip() for x in raw_leagues.split(",") if x.strip()} or None
    raw_excludes=os.environ.get("MATRIX_EXTENDED_BOOTSTRAP_EXCLUDE_DATASETS","").strip()
    exclude_paths=tuple(Path(x.strip()) for x in raw_excludes.split(";") if x.strip())
    r=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path(os.environ.get("MATRIX_EXTENDED_BOOTSTRAP_OUTPUT_DIR","evidence/api_football/market_expansion/historical_bootstrap")),
        max_fixtures=int(os.environ.get("MATRIX_EXTENDED_BOOTSTRAP_MAX_FIXTURES","100")),
        daily_reserve=int(os.environ.get("MATRIX_API_FOOTBALL_DAILY_RESERVE","5000")),
        allowed_leagues=allowed_leagues,
        exclude_dataset_paths=exclude_paths,
    )
    print(json.dumps({
        "status":r["status"],
        "selected_fixture_count":r["selected_fixture_count"],
        "captured_fixture_count":r["captured_fixture_count"],
        "team_statistics_covered_count":r["team_statistics_covered_count"],
        "player_statistics_covered_count":r["player_statistics_covered_count"],
        "network_calls":r["network_calls"],
        "last_daily_remaining":r["last_daily_remaining"],
        "stopped_reason":r["stopped_reason"],
        "real_money":r["real_money"],
    },sort_keys=True))

if __name__=="__main__":
    main()
