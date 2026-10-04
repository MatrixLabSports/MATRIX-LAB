from __future__ import annotations

import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.providers.api_football.client import ApiFootballClient
from app.providers.api_football.config import ApiFootballConfig

SAMPLE_SIZE=8

def _norm(v:Any)->str:
    return " ".join(str(v or "").strip().casefold().replace("_"," ").split())

def _sha(payload:Any)->str:
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def _load_ids(path:Path)->list[str]:
    ids=[]
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            fid=str(json.loads(raw).get("fixture_id") or "").strip()
            if fid: ids.append(fid)
    out=[]
    for fid in reversed(ids):
        if fid not in out: out.append(fid)
        if len(out)>=SAMPLE_SIZE: break
    return list(reversed(out))

def _team(payload:Any)->dict[str,bool]:
    types=set()
    for team in (payload.get("response") or []) if isinstance(payload,Mapping) else []:
        if not isinstance(team,Mapping): continue
        for item in team.get("statistics") or []:
            if isinstance(item,Mapping): types.add(_norm(item.get("type")))
    return {
        "corners":bool(types & {"corner kicks","corners"}),
        "team_shots_on_target":bool(types & {"shots on goal","shots on target"}),
        "team_total_shots":"total shots" in types,
        "cards":bool(types & {"yellow cards","red cards"}),
        "team_fouls":"fouls" in types,
    }

def _has(d:Any,*keys:str)->bool:
    cur=d
    for k in keys:
        if not isinstance(cur,Mapping): return False
        cur=cur.get(k)
    return cur is not None

def _players(payload:Any)->dict[str,bool]:
    f={k:False for k in ("player_shots","player_shots_on_target","goalkeeper_saves","player_assists","player_passes","player_tackles","player_fouls")}
    for team in (payload.get("response") or []) if isinstance(payload,Mapping) else []:
        if not isinstance(team,Mapping): continue
        for row in team.get("players") or []:
            if not isinstance(row,Mapping): continue
            for s in row.get("statistics") or []:
                if not isinstance(s,Mapping): continue
                f["player_shots"]|=_has(s,"shots","total")
                f["player_shots_on_target"]|=_has(s,"shots","on")
                f["goalkeeper_saves"]|=_has(s,"goals","saves")
                f["player_assists"]|=_has(s,"goals","assists")
                f["player_passes"]|=_has(s,"passes","total")
                f["player_tackles"]|=_has(s,"tackles","total")
                f["player_fouls"]|=_has(s,"fouls","committed")
    return f

def run(out_dir:Path, client:ApiFootballClient|None=None, fixture_ids:list[str]|None=None)->dict[str,Any]:
    client=client or ApiFootballClient(ApiFootballConfig.from_environment())
    fixture_ids=fixture_ids or _load_ids(Path("evidence/api_football/prospective_calibration/ledger.jsonl"))
    if not fixture_ids: raise ValueError("NO_SETTLED_FIXTURES")
    out_dir.mkdir(parents=True,exist_ok=True)
    counters={k:0 for k in ("corners","team_shots_on_target","team_total_shots","cards","team_fouls","player_shots","player_shots_on_target","goalkeeper_saves","player_assists","player_passes","player_tackles","player_fouls")}
    captures=[]
    for fid in fixture_ids:
        a=client.get("/fixtures/statistics",{"fixture":fid})
        b=client.get("/fixtures/players",{"fixture":fid})
        (out_dir/f"fixture_{fid}_statistics.json").write_text(json.dumps(a,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
        (out_dir/f"fixture_{fid}_players.json").write_text(json.dumps(b,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
        ta,pb=_team(a),_players(b)
        for k,v in {**ta,**pb}.items(): counters[k]+=int(v)
        captures.append({"fixture_id":fid,"statistics_sha256":_sha(a),"players_sha256":_sha(b),"team_fields":ta,"player_fields":pb})
    mappings={"corners","cards","player_shots","player_shots_on_target","player_assists","player_passes"}
    states={}
    for name,field in {
        "CORNERS_OVER_UNDER":"corners","TEAM_SHOTS_ON_TARGET":"team_shots_on_target",
        "PLAYER_SHOTS":"player_shots","PLAYER_SHOTS_ON_TARGET":"player_shots_on_target",
        "GOALKEEPER_SAVES":"goalkeeper_saves","CARDS_OVER_UNDER":"cards",
        "PLAYER_ASSISTS":"player_assists","PLAYER_PASSES":"player_passes",
        "PLAYER_TACKLES":"player_tackles","PLAYER_FOULS":"player_fouls",
    }.items():
        states[name]={"source_field":field,"coverage":counters[field],"sampled_fixtures":len(fixture_ids),
            "source_coverage_status":"SOURCE_FIELD_OBSERVED" if counters[field] else "NOT_OBSERVED_IN_SAMPLE",
            "canonical_price_mapping":"EXISTS_R2" if field in mappings else "MISSING_OR_REQUIRES_NEW_SCOPE",
            "model_status":"NOT_YET_MODELED_PROSPECTIVELY"}
    manifest={"schema":"MATRIX_FOOTBALL_EXTENDED_MARKET_COVERAGE_PROBE_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_football","sample_fixture_ids":fixture_ids,"sampled_fixture_count":len(fixture_ids),
        "network_calls":len(fixture_ids)*2,"captures":captures,"field_coverage_counts":counters,
        "market_state":states,"purpose":"SOURCE_COVERAGE_ONLY_NOT_MODEL_VALIDATION",
        "outcomes_used_for_model_tuning":False,"odds_used_to_generate_probability":False,
        "p_matrix_status":"NOT_GENERATED_FOR_EXTENDED_MARKETS","automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"}
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest

def main():
    raw_ids=os.environ.get("MATRIX_API_FOOTBALL_EXTENDED_FIXTURE_IDS","").strip()
    fixture_ids=[x.strip() for x in raw_ids.split(",") if x.strip()] or None
    r=run(Path("evidence/api_football/market_expansion/coverage_probe"),fixture_ids=fixture_ids)
    print(json.dumps({"status":r["status"],"network_calls":r["network_calls"],"field_coverage_counts":r["field_coverage_counts"],"real_money":r["real_money"]},sort_keys=True))

if __name__=="__main__":
    main()
