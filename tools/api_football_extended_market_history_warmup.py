from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools.api_football_extended_market_historical_bootstrap import (
    _player_rows,
    _request,
    _stat_map,
)

FINAL_STATUSES={"FT","AET","PEN"}
RAW_PATHS=(
    Path("evidence/api_football/history/raw/league_72_season_2026.bin"),
    Path("evidence/api_football/history/raw/league_252_season_2026.bin"),
)
EXISTING_DATASETS=(
    Path("evidence/api_football/market_expansion/historical_bootstrap/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3/normalized_dataset.jsonl"),
)
TIMEOUT_SLEEP=0.20


def _utc(v:object)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _existing_ids(paths=EXISTING_DATASETS)->set[str]:
    ids=set()
    for path in paths:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row=json.loads(raw)
                if row.get("fixture_id") is not None:
                    ids.add(str(row["fixture_id"]))
    return ids


def _protected_ids_and_cutoff()->tuple[set[str],datetime]:
    seal=json.loads(Path("evidence/api_football/challenger/final_holdout_seal.json").read_text(encoding="utf-8"))
    rows=seal.get("rows")
    if not isinstance(rows,list) or not rows:
        raise ValueError("FINAL_HOLDOUT_ROWS_MISSING")
    ids={str(r["fixture_id"]) for r in rows}
    cutoff=min(_utc(r["kickoff_utc"]) for r in rows)
    return ids,cutoff


def _prospective_ids()->set[str]:
    path=Path("evidence/api_football/prospective_calibration/ledger.jsonl")
    ids=set()
    if not path.exists():
        return ids
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw)
            if row.get("fixture_id") is not None:
                ids.add(str(row["fixture_id"]))
    return ids


def _raw_final_candidates()->list[dict[str,Any]]:
    out=[]
    for path in RAW_PATHS:
        payload=json.loads(path.read_bytes().decode("utf-8"))
        response=payload.get("response") if isinstance(payload,Mapping) else None
        if not isinstance(response,list):
            continue
        for raw in response:
            if not isinstance(raw,Mapping):
                continue
            fixture=raw.get("fixture"); teams=raw.get("teams"); league=raw.get("league")
            if not isinstance(fixture,Mapping) or not isinstance(teams,Mapping) or not isinstance(league,Mapping):
                continue
            status=fixture.get("status")
            if not isinstance(status,Mapping) or str(status.get("short") or "").upper().strip() not in FINAL_STATUSES:
                continue
            home=teams.get("home"); away=teams.get("away")
            if not isinstance(home,Mapping) or not isinstance(away,Mapping):
                continue
            try:
                fid=str(int(fixture.get("id")))
                hid=str(int(home.get("id")))
                aid=str(int(away.get("id")))
                kickoff=_utc(fixture.get("date"))
            except (TypeError,ValueError):
                continue
            out.append({
                "fixture_id":fid,
                "kickoff_utc":kickoff.isoformat(),
                "league_id":str(league.get("id") or ""),
                "season":league.get("season"),
                "home_team_id":hid,
                "away_team_id":aid,
                "home_team_name":str(home.get("name") or ""),
                "away_team_name":str(away.get("name") or ""),
                "source_path":str(path),
            })
    out.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
    return out


def select_candidates(limit:int)->tuple[list[dict[str,Any]],dict[str,Any]]:
    existing=_existing_ids()
    protected,cutoff=_protected_ids_and_cutoff()
    prospective=_prospective_ids()
    raw=_raw_final_candidates()
    selected=[
        r for r in raw
        if r["fixture_id"] not in existing
        and r["fixture_id"] not in protected
        and r["fixture_id"] not in prospective
        and _utc(r["kickoff_utc"]) < cutoff
    ][:limit]
    audit={
        "raw_final_count":len(raw),
        "existing_exclusion_count":len(existing),
        "protected_final_holdout_count":len(protected),
        "prospective_exclusion_count":len(prospective),
        "development_cutoff_utc":cutoff.isoformat(),
        "selected_count":len(selected),
    }
    return selected,audit


def run(api_key:str,out_dir:Path,max_fixtures:int=80,daily_reserve:int=5000,session:Any|None=None)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    if max_fixtures<1 or max_fixtures>120:
        raise ValueError("MAX_FIXTURES_OUT_OF_POLICY")
    selected,audit=select_candidates(max_fixtures)
    client=session or requests.Session()
    out_dir.mkdir(parents=True,exist_ok=True)
    raw_dir=out_dir/"raw"; raw_dir.mkdir(parents=True,exist_ok=True)
    normalized=[]
    captures=[]
    calls=0
    remaining=None
    stopped_reason=None

    for src in selected:
        if remaining is not None and int(remaining) <= daily_reserve:
            stopped_reason="DAILY_RESERVE_REACHED"
            break
        fid=src["fixture_id"]
        stat,sbody,sok,srem,sstatus=_request(client,key,"/fixtures/statistics",fid)
        calls+=1
        remaining=srem
        (raw_dir/f"fixture_{fid}_statistics.bin").write_bytes(sbody)
        stat_sha=hashlib.sha256(sbody).hexdigest()
        team_stats=_stat_map(stat) if sok else {}
        if not sok or not team_stats:
            captures.append({
                "fixture_id":fid,
                "status":"NO_TEAM_STATISTICS",
                "http_status":sstatus,
                "statistics_sha256":stat_sha,
            })
            continue
        time.sleep(TIMEOUT_SLEEP)

        players,pbody,pok,prem,pstatus=_request(client,key,"/fixtures/players",fid)
        calls+=1
        remaining=prem
        (raw_dir/f"fixture_{fid}_players.bin").write_bytes(pbody)
        player_sha=hashlib.sha256(pbody).hexdigest()
        player_rows=_player_rows(players) if pok else []

        normalized.append({
            **src,
            "team_statistics":team_stats,
            "player_statistics":player_rows,
            "statistics_sha256":stat_sha,
            "players_sha256":player_sha,
            "development_role":"HISTORICAL_WARMUP_AND_DEVELOPMENT",
            "protected_holdout_member":False,
            "prospective_calibration_member":False,
        })
        captures.append({
            "fixture_id":fid,
            "status":"CAPTURED",
            "team_statistics_present":True,
            "player_statistics_present":bool(player_rows),
            "player_row_count":len(player_rows),
            "statistics_sha256":stat_sha,
            "players_sha256":player_sha,
        })
        time.sleep(TIMEOUT_SLEEP)

    dataset=out_dir/"normalized_dataset.jsonl"
    dataset.write_text(
        "".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in normalized),
        encoding="utf-8",
    )
    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_HISTORY_WARMUP_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **audit,
        "captured_fixture_count":len(normalized),
        "team_statistics_covered_count":sum(1 for r in captures if r.get("team_statistics_present")),
        "player_statistics_covered_count":sum(1 for r in captures if r.get("player_statistics_present")),
        "network_calls":calls,
        "daily_reserve_policy":daily_reserve,
        "last_daily_remaining":remaining,
        "stopped_reason":stopped_reason,
        "dataset_path":str(dataset),
        "dataset_sha256":hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "captures":captures,
        "protected_holdout_intersection_count":0,
        "prospective_intersection_count":0,
        "feature_usage_policy":"TARGET_FEATURES_MUST_USE_STRICTLY_EARLIER_MATCHES_ONLY",
        "odds_used_to_generate_probability":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )
    return manifest


def main()->None:
    result=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path("evidence/api_football/market_expansion/historical_warmup"),
        max_fixtures=int(os.environ.get("MATRIX_EXTENDED_WARMUP_MAX_FIXTURES","80")),
        daily_reserve=int(os.environ.get("MATRIX_API_FOOTBALL_DAILY_RESERVE","5000")),
    )
    print(json.dumps({
        "status":result["status"],
        "selected_count":result["selected_count"],
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
