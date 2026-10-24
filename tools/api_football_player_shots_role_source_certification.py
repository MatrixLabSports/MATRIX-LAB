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
TIMEOUT=20.0
MIN_FIXTURES=5
MIN_COMPARABLE_PLAYERS=30
MIN_ROLE_AGREEMENT=0.98
MAX_FIXTURES_TO_QUERY=16

def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def _lineup_roles(payload:Mapping[str,Any])->dict[str,str]:
    roles={}
    for team_row in payload.get("response") or []:
        if not isinstance(team_row,Mapping): continue
        for key,role in (("startXI","STARTER"),("substitutes","SUBSTITUTE")):
            for item in team_row.get(key) or []:
                p=item.get("player") if isinstance(item,Mapping) and isinstance(item.get("player"),Mapping) else {}
                pid=str(p.get("id") or "")
                if not pid: continue
                if pid in roles and roles[pid]!=role:
                    raise ValueError("LINEUP_PLAYER_ROLE_CONFLICT:"+pid)
                roles[pid]=role
    return roles

def run(api_key:str,out_root:Path)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    source=Path("evidence/api_football/market_expansion/player_shots_expected_minutes_v2/player_shots_role_expected_minutes_pit.jsonl")
    model_path=Path("evidence/api_football/market_expansion/player_shots_expected_minutes_v2/model.json")
    rows=_load_jsonl(source)
    train=[r for r in rows if r.get("split")=="TRAIN"]
    model=json.loads(model_path.read_text(encoding="utf-8"))
    grouped=defaultdict(list)
    for r in train:
        grouped[str(r["fixture_id"])].append(r)
    # Prefer fixtures with the most comparable players; tie-break by latest kickoff.
    candidates=sorted(grouped.items(),key=lambda kv:(len(kv[1]),str(kv[1][0]["kickoff_utc"]),kv[0]),reverse=True)[:MAX_FIXTURES_TO_QUERY]
    now=datetime.now(timezone.utc).replace(microsecond=0)
    run_id=now.strftime("%Y%m%dT%H%M%SZ")
    run_dir=out_root/"runs"/run_id
    raw_dir=run_dir/"raw"; raw_dir.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    fixture_records=[]; comparable=0; matches=0; missing=0; mismatch_rows=[]
    for fid,frows in candidates:
        resp=session.get(BASE_URL+"/fixtures/lineups",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        body=bytes(resp.content)
        (raw_dir/f"fixture_{fid}_lineups.bin").write_bytes(body)
        try: payload=resp.json()
        except ValueError: payload={}
        roles=_lineup_roles(payload) if 200<=int(resp.status_code)<300 else {}
        local_comp=local_match=local_missing=0
        for row in frows:
            pid=str(row["player_id"])
            expected=str(row["lineup_role_reconstructed"])
            observed=roles.get(pid)
            if observed is None:
                local_missing+=1; missing+=1
                continue
            comparable+=1; local_comp+=1
            if observed==expected:
                matches+=1; local_match+=1
            else:
                mismatch_rows.append({
                    "fixture_id":fid,"player_id":pid,"player_name":row.get("player_name"),
                    "historical_role":expected,"lineup_role":observed
                })
        fixture_records.append({
            "fixture_id":fid,"kickoff_utc":frows[0]["kickoff_utc"],
            "http_status":int(resp.status_code),"lineup_player_count":len(roles),
            "comparable_player_count":local_comp,"role_match_count":local_match,
            "dataset_player_missing_from_lineup":local_missing,
            "raw_sha256":hashlib.sha256(body).hexdigest(),
        })
    fixtures_with_comparison=sum(r["comparable_player_count"]>0 for r in fixture_records)
    agreement=(matches/comparable) if comparable else 0.0
    historical_gate=(
        model.get("status")=="HISTORICAL_OOS_PASS_ROLE_AWARE_PROSPECTIVE_BLOCKED"
        and bool(model.get("validation",{}).get("gate_passed"))
        and model.get("current_match_minutes_used_as_feature") is False
        and model.get("selected_parameters",{}).get("expected_minutes_method")=="MEAN_PRIOR_SAME_ROLE_MINUTES_ONLY"
    )
    source_certified=(
        fixtures_with_comparison>=MIN_FIXTURES
        and comparable>=MIN_COMPARABLE_PLAYERS
        and agreement>=MIN_ROLE_AGREEMENT
    )
    expected_minutes_certified=bool(source_certified and historical_gate)
    freeze_allowed=expected_minutes_certified
    payload={
        "schema":"MATRIX_PLAYER_SHOTS_ROLE_SOURCE_CERTIFICATION_V1",
        "run_id":run_id,"observed_at_utc":now.isoformat(),
        "source_dataset_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "model_blob_reference":model.get("selected_parameters_sha256"),
        "historical_role_source":"fixtures/players.games.substitute",
        "prospective_role_source":"/fixtures/lineups",
        "training_rows_only_used_for_source_certification":True,
        "final_50_validation_rows_used_for_source_certification":False,
        "fixtures_queried":len(fixture_records),
        "fixtures_with_comparison":fixtures_with_comparison,
        "comparable_player_roles":comparable,
        "matching_player_roles":matches,
        "missing_player_roles":missing,
        "mismatch_count":len(mismatch_rows),
        "role_agreement_rate":agreement,
        "requirements":{"min_fixtures":MIN_FIXTURES,"min_comparable_players":MIN_COMPARABLE_PLAYERS,"min_role_agreement":MIN_ROLE_AGREEMENT},
        "cross_source_role_equivalence_certified":source_certified,
        "prematch_lineup_source_certified":source_certified,
        "expected_minutes_algorithm_historical_oos_validated":historical_gate,
        "expected_minutes_pit_prospective_certified":expected_minutes_certified,
        "prospective_freeze_allowed":freeze_allowed,
        "fixture_records":fixture_records,
        "mismatches":mismatch_rows,
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS" if freeze_allowed else "BLOCKED",
    }
    manifest=run_dir/"manifest.json"
    manifest.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    out_root.mkdir(parents=True,exist_ok=True)
    last=out_root/"last_run.json"
    last.write_text(json.dumps({
        "schema":"MATRIX_PLAYER_SHOTS_ROLE_SOURCE_CERTIFICATION_POINTER_V1",
        "run_id":run_id,"manifest_path":str(manifest),
        "manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "role_agreement_rate":agreement,
        "comparable_player_roles":comparable,
        "fixtures_with_comparison":fixtures_with_comparison,
        "cross_source_role_equivalence_certified":source_certified,
        "expected_minutes_pit_prospective_certified":expected_minutes_certified,
        "prospective_freeze_allowed":freeze_allowed,
        "status":payload["status"],"real_money":"BLOCKED"
    },indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":payload["status"],"agreement":agreement,"comparable":comparable,"fixtures":fixtures_with_comparison,"freeze_allowed":freeze_allowed},sort_keys=True))
    return payload

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/market_expansion/player_shots_role_certification"))
