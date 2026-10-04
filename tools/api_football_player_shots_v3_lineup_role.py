from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from math import exp, floor, log
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20.0
MIN_OVERALL_HISTORY=5
MIN_ROLE_HISTORY=3
MAX_OVERALL_HISTORY=20
MAX_ROLE_HISTORY=10
MIN_TRAIN=200
MIN_VALIDATION=50
EPS=1e-15

DATASET_DIRS=(
    Path("evidence/api_football/market_expansion/historical_prior_season"),
    Path("evidence/api_football/market_expansion/historical_bootstrap"),
    Path("evidence/api_football/market_expansion/historical_warmup"),
    Path("evidence/api_football/market_expansion/historical_statsrich"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3"),
)


def _utc(value:object)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _fixture_sources()->list[dict[str,Any]]:
    by_id={}
    for root in DATASET_DIRS:
        dataset=root/"normalized_dataset.jsonl"
        if not dataset.exists():
            continue
        for raw in dataset.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row=json.loads(raw)
            fid=str(row.get("fixture_id") or "").strip()
            kickoff=row.get("kickoff_utc")
            if not fid or not kickoff or fid in by_id:
                continue
            by_id[fid]={
                "fixture_id":fid,
                "kickoff_utc":kickoff,
                "league_id":str(row.get("league_id") or ""),
                "season":row.get("season"),
                "raw_players_path":str(root/"raw"/f"fixture_{fid}_players.bin"),
            }
    return sorted(by_id.values(),key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))


def _load_apps(path:Path)->list[dict[str,Any]]:
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeDecodeError,json.JSONDecodeError):
        return []
    out=[]
    for team_row in payload.get("response") or []:
        if not isinstance(team_row,Mapping):
            continue
        team=team_row.get("team") if isinstance(team_row.get("team"),Mapping) else {}
        for player_row in team_row.get("players") or []:
            if not isinstance(player_row,Mapping):
                continue
            player=player_row.get("player") if isinstance(player_row.get("player"),Mapping) else {}
            pid=str(player.get("id") or "").strip()
            if not pid or pid=="0":
                continue
            for stat in player_row.get("statistics") or []:
                if not isinstance(stat,Mapping):
                    continue
                games=stat.get("games") if isinstance(stat.get("games"),Mapping) else {}
                shots=stat.get("shots") if isinstance(stat.get("shots"),Mapping) else {}
                minutes=games.get("minutes")
                shot_count=shots.get("total")
                if minutes is None or shot_count is None:
                    continue
                try:
                    minutes_f=float(minutes); shots_f=float(shot_count)
                except (TypeError,ValueError):
                    continue
                if minutes_f<=0 or shots_f<0:
                    continue
                out.append({
                    "player_id":pid,
                    "player_name":player.get("name"),
                    "team_id":str(team.get("id") or ""),
                    "team_name":team.get("name"),
                    "minutes":minutes_f,
                    "shots":shots_f,
                })
                break
    return out


def _roles_from_lineup(payload:Mapping[str,Any])->dict[str,str]:
    roles={}
    for team_row in payload.get("response") or []:
        if not isinstance(team_row,Mapping):
            continue
        for key,role in (("startXI","STARTER"),("substitutes","SUBSTITUTE")):
            for item in team_row.get(key) or []:
                p=item.get("player") if isinstance(item,Mapping) and isinstance(item.get("player"),Mapping) else {}
                pid=str(p.get("id") or "").strip()
                if not pid or pid=="0":
                    continue
                previous=roles.get(pid)
                if previous and previous!=role:
                    raise ValueError("LINEUP_ROLE_CONFLICT:"+pid)
                roles[pid]=role
    return roles


def _request_lineup(session:requests.Session,key:str,fid:str)->tuple[dict[str,Any],bytes,int]:
    last_status=0
    for attempt in range(5):
        resp=session.get(BASE_URL+"/fixtures/lineups",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        last_status=int(resp.status_code)
        body=bytes(resp.content)
        if last_status==429:
            time.sleep(min(60,5*(attempt+1)))
            continue
        if not 200<=last_status<300:
            raise RuntimeError(f"LINEUP_HTTP_{last_status}:{fid}")
        try:
            payload=resp.json()
        except ValueError as exc:
            raise RuntimeError("LINEUP_NON_JSON:"+fid) from exc
        if not isinstance(payload,dict):
            raise RuntimeError("LINEUP_ROOT_NOT_OBJECT:"+fid)
        return payload,body,last_status
    raise RuntimeError(f"LINEUP_RATE_LIMIT_EXHAUSTED:{fid}:{last_status}")


def collect_lineups(api_key:str,out_dir:Path)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    fixtures=_fixture_sources()
    cache_path=out_dir/"lineup_role_cache.jsonl"
    existing={}
    if cache_path.exists():
        for raw in cache_path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row=json.loads(raw)
                existing[str(row["fixture_id"])]=row
    session=requests.Session()
    calls=0
    rows=[]
    raw_bundle=out_dir/"lineup_raw_bundle.jsonl.gz"
    out_dir.mkdir(parents=True,exist_ok=True)
    raw_records=[]
    for idx,fixture in enumerate(fixtures,1):
        fid=fixture["fixture_id"]
        if fid in existing and existing[fid].get("status")=="PASS":
            rows.append(existing[fid]); continue
        payload,body,status=_request_lineup(session,key,fid)
        calls+=1
        roles=_roles_from_lineup(payload)
        row={
            "fixture_id":fid,
            "kickoff_utc":fixture["kickoff_utc"],
            "league_id":fixture["league_id"],
            "season":fixture["season"],
            "role_count":len(roles),
            "roles":roles,
            "provider":"api_football",
            "endpoint":"/fixtures/lineups",
            "http_status":status,
            "raw_sha256":hashlib.sha256(body).hexdigest(),
            "status":"PASS" if roles else "NO_LINEUP",
        }
        rows.append(row)
        raw_records.append({"fixture_id":fid,"raw_utf8":body.decode("utf-8","replace")})
        if calls and calls%50==0:
            time.sleep(0.5)
    rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
    cache_path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    if raw_records:
        mode="at" if raw_bundle.exists() else "wt"
        with gzip.open(raw_bundle,mode,encoding="utf-8") as gz:
            for rec in raw_records:
                gz.write(json.dumps(rec,sort_keys=True,ensure_ascii=False)+"\n")
    available=sum(r["status"]=="PASS" for r in rows)
    manifest={
        "schema":"MATRIX_PLAYER_SHOTS_V3_LINEUP_CACHE_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fixture_count":len(fixtures),
        "lineup_available_count":available,
        "lineup_missing_count":len(fixtures)-available,
        "network_calls_this_run":calls,
        "cache_path":str(cache_path),
        "cache_sha256":hashlib.sha256(cache_path.read_bytes()).hexdigest(),
        "raw_bundle_path":str(raw_bundle),
        "raw_bundle_sha256":hashlib.sha256(raw_bundle.read_bytes()).hexdigest() if raw_bundle.exists() else None,
        "role_source":"/fixtures/lineups",
        "games_substitute_used":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS" if available>=MIN_TRAIN else "INSUFFICIENT_LINEUP_COVERAGE",
    }
    (out_dir/"lineup_cache_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def _mean(vals:list[float])->float:
    return sum(vals)/len(vals)


def _rate90(rows:list[dict[str,Any]])->float:
    mins=sum(float(x["minutes"]) for x in rows)
    if mins<=0:
        raise ValueError("NONPOSITIVE_MINUTES")
    return 90*sum(float(x["shots"]) for x in rows)/mins


def build_dataset(out_dir:Path)->dict[str,Any]:
    fixtures=_fixture_sources()
    cache={}
    for raw in (out_dir/"lineup_role_cache.jsonl").read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw); cache[str(row["fixture_id"])]=row
    history=defaultdict(list)
    rows=[]
    skipped_no_lineup=0
    skipped_missing_role=0
    insufficient_overall=0
    insufficient_role=0
    for fixture in fixtures:
        roles=(cache.get(fixture["fixture_id"]) or {}).get("roles") or {}
        if not roles:
            skipped_no_lineup+=1
            continue
        apps=_load_apps(Path(fixture["raw_players_path"]))
        pending=[]
        for app in apps:
            role=roles.get(app["player_id"])
            if role not in {"STARTER","SUBSTITUTE"}:
                skipped_missing_role+=1
                continue
            app={**app,"role":role}
            pid=app["player_id"]
            prior=history[pid][-MAX_OVERALL_HISTORY:]
            if len(prior)<MIN_OVERALL_HISTORY:
                insufficient_overall+=1
            else:
                role_prior=[x for x in prior if x["role"]==role][-MAX_ROLE_HISTORY:]
                if len(role_prior)<MIN_ROLE_HISTORY:
                    insufficient_role+=1
                else:
                    role_recent=role_prior[-3:]
                    last5=prior[-5:]
                    rows.append({
                        "fixture_id":fixture["fixture_id"],
                        "kickoff_utc":fixture["kickoff_utc"],
                        "league_id":fixture["league_id"],
                        "season":fixture["season"],
                        "player_id":pid,
                        "player_name":app["player_name"],
                        "team_id":app["team_id"],
                        "team_name":app["team_name"],
                        "lineup_role":role,
                        "historical_role_label_source":"/fixtures/lineups",
                        "games_substitute_used":False,
                        "prior_appearance_count":len(prior),
                        "prior_role_appearance_count":len(role_prior),
                        "prior_mean_count":_mean([float(x["shots"]) for x in prior]),
                        "last5_mean_count":_mean([float(x["shots"]) for x in last5]),
                        "prior_mean_minutes":_mean([float(x["minutes"]) for x in prior]),
                        "last5_mean_minutes":_mean([float(x["minutes"]) for x in last5]),
                        "role_prior_shots_per90":_rate90(role_prior),
                        "role_recent3_shots_per90":_rate90(role_recent),
                        "expected_minutes_pit":_mean([float(x["minutes"]) for x in role_prior]),
                        "expected_minutes_source":"MEAN_PRIOR_SAME_ROLE_MINUTES_ONLY",
                        "target_shots":float(app["shots"]),
                        "current_match_minutes_postsettlement_audit_only":float(app["minutes"]),
                        "current_match_minutes_used_as_feature":False,
                        "same_match_shots_used_in_features":False,
                    })
            pending.append(app)
        for app in pending:
            history[app["player_id"]].append({
                "fixture_id":fixture["fixture_id"],
                "kickoff_utc":fixture["kickoff_utc"],
                "role":app["role"],
                "minutes":float(app["minutes"]),
                "shots":float(app["shots"]),
            })
    rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"]),int(r["player_id"])))
    val_n=MIN_VALIDATION if len(rows)>=MIN_TRAIN+MIN_VALIDATION else 0
    split=len(rows)-val_n
    for i,row in enumerate(rows):
        row["split"]="TRAIN" if i<split else "VALIDATION"
    path=out_dir/"player_shots_v3_pit.jsonl"
    path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    manifest={
        "schema":"MATRIX_PLAYER_SHOTS_V3_PIT_DATASET_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "row_count":len(rows),"train_count":split,"validation_count":val_n,
        "fixture_source_count":len(fixtures),
        "skipped_fixture_no_lineup":skipped_no_lineup,
        "skipped_player_missing_lineup_role":skipped_missing_role,
        "insufficient_overall_history_count":insufficient_overall,
        "insufficient_same_role_history_count":insufficient_role,
        "minimum_overall_history":MIN_OVERALL_HISTORY,
        "minimum_same_role_history":MIN_ROLE_HISTORY,
        "feature_policy":"STRICTLY_PRIOR_APPEARANCES_AND_PRIOR_SAME_LINEUP_ROLE_MINUTES_ONLY",
        "historical_role_label_source":"/fixtures/lineups",
        "prospective_role_label_source":"/fixtures/lineups",
        "games_substitute_used":False,
        "current_match_minutes_used_as_feature":False,
        "same_match_target_used_in_features":False,
        "dataset_path":str(path),
        "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS" if val_n==MIN_VALIDATION else "INSUFFICIENT_ROLE_AWARE_SAMPLE",
    }
    (out_dir/"dataset_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _poisson_over(mu:float,line:float)->float:
    mu=max(0.01,float(mu)); cut=int(floor(line))
    term=exp(-mu); cdf=term
    for k in range(1,cut+1):
        term*=mu/k; cdf+=term
    return _clip(1-cdf)


def _metrics(ys:list[int],ps:list[float])->dict[str,float]:
    brier=ll=0.0; bins=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0); brier+=(p-y)**2
        ll+=-(y*log(p)+(1-y)*log(1-p))
        bins[min(4,int(p*5))].append((y,p))
    n=len(ys); ece=0.0; mx=0.0
    for b in bins:
        if not b: continue
        obs=sum(y for y,_ in b)/len(b); pred=sum(p for _,p in b)/len(b)
        err=abs(obs-pred); ece+=len(b)/n*err; mx=max(mx,err)
    return {"sample_size":n,"brier_score":brier/n,"log_loss":ll/n,"ece_5bin":ece,"max_calibration_error_5bin":mx}


def _v3_mu(row:Mapping[str,Any],alpha:float)->float:
    long=max(0.0,float(row["role_prior_shots_per90"]))
    recent=max(0.0,float(row["role_recent3_shots_per90"]))
    rate=(1-alpha)*long+alpha*recent
    mins=max(1.0,min(90.0,float(row["expected_minutes_pit"])))
    return max(0.01,rate*mins/90.0)


def _role_agnostic_mu(row:Mapping[str,Any],alpha:float,beta:float)->float:
    long=max(0.0,float(row["prior_mean_count"]))
    recent=max(0.0,float(row["last5_mean_count"]))
    prior_m=max(1.0,float(row["prior_mean_minutes"]))
    recent_m=max(1.0,float(row["last5_mean_minutes"]))
    count=(1-alpha)*long+alpha*recent
    ratio=min(1.5,max(0.5,recent_m/prior_m))
    return max(0.01,count*(ratio**beta))


def build_model(out_dir:Path)->dict[str,Any]:
    rows=[json.loads(x) for x in (out_dir/"player_shots_v3_pit.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    train=[r for r in rows if r["split"]=="TRAIN"]
    val=[r for r in rows if r["split"]=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(val)<MIN_VALIDATION:
        return {"schema":"MATRIX_PLAYER_SHOTS_V3_MODEL_V1","status":"REJECTED_INSUFFICIENT_OOS","prospective_eligible":False,"real_money":"BLOCKED"}
    line=1.5
    cut=max(150,int(len(train)*0.8)); cut=min(cut,len(train)-25)
    inner=train[cut:]
    trials=[]
    for alpha in (0.0,0.25,0.5,0.75,1.0):
        ys=[int(float(r["target_shots"])>line) for r in inner]
        ps=[_poisson_over(_v3_mu(r,alpha),line) for r in inner]
        trials.append({"alpha_recent_rate":alpha,"metrics":_metrics(ys,ps)})
    trials.sort(key=lambda x:(x["metrics"]["log_loss"],x["metrics"]["brier_score"]))
    selected=trials[0]
    # Frozen role-agnostic comparator on the same v3 rows, selected using TRAIN only.
    comp_trials=[]
    for a in (0.0,0.25,0.5,0.75,1.0):
        for b in (0.0,0.5,1.0):
            ys=[int(float(r["target_shots"])>line) for r in inner]
            ps=[_poisson_over(_role_agnostic_mu(r,a,b),line) for r in inner]
            comp_trials.append({"alpha":a,"beta":b,"metrics":_metrics(ys,ps)})
    comp_trials.sort(key=lambda x:(x["metrics"]["log_loss"],x["metrics"]["brier_score"]))
    comp=comp_trials[0]
    ys=[int(float(r["target_shots"])>line) for r in val]
    p3=[_poisson_over(_v3_mu(r,float(selected["alpha_recent_rate"])),line) for r in val]
    pc=[_poisson_over(_role_agnostic_mu(r,float(comp["alpha"]),float(comp["beta"])),line) for r in val]
    m3=_metrics(ys,p3); mc=_metrics(ys,pc)
    db=m3["brier_score"]-mc["brier_score"]
    dl=m3["log_loss"]-mc["log_loss"]
    passed=(db<0 and dl<0 and m3["ece_5bin"]<=0.10 and m3["max_calibration_error_5bin"]<=0.20)
    params={
        "alpha_recent_rate":selected["alpha_recent_rate"],
        "expected_minutes_method":"MEAN_PRIOR_SAME_LINEUP_ROLE_MINUTES_ONLY",
        "minimum_same_role_history":MIN_ROLE_HISTORY,
        "evaluation_line":line,
        "role_source":"/fixtures/lineups",
    }
    result={
        "schema":"MATRIX_PLAYER_SHOTS_V3_MODEL_V1",
        "lane":"PLAYER_SHOTS_OVER_1_5",
        "candidate":"lineup_role_expected_minutes_v3",
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION_V3" if passed else "REJECTED_HISTORICAL_OOS_V3",
        "row_count":len(rows),"train_count":len(train),"validation_count":len(val),
        "evaluation_line":line,
        "historical_role_source":"/fixtures/lineups",
        "prospective_role_source":"/fixtures/lineups",
        "games_substitute_used":False,
        "selected_parameters":params,
        "selected_parameters_sha256":hashlib.sha256(json.dumps(params,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "internal_selection":{"selection_rows":len(inner),"trial_count":len(trials),"selected":selected,"final_validation_used_for_selection":False},
        "comparator_selection":{"selection_rows":len(inner),"trial_count":len(comp_trials),"selected":comp,"final_validation_used_for_selection":False},
        "validation":{
            "challenger_v3":m3,
            "role_agnostic_same_rows":mc,
            "delta_brier_v3_minus_role_agnostic":db,
            "delta_log_loss_v3_minus_role_agnostic":dl,
            "gate_passed":passed,
        },
        "prospective_eligible":passed,
        "prospective_gates":[30,50,100,200] if passed else [],
        "validation_used_for_parameter_tuning":False,
        "protected_final_holdout_used":False,
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    (out_dir/"model.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result


def initialize_prospective(out_dir:Path,model:dict[str,Any])->dict[str,Any]:
    target=Path("evidence/api_football/player_shots_v3_prospective")
    target.mkdir(parents=True,exist_ok=True)
    eligible=bool(model.get("prospective_eligible"))
    for name in ("freeze_ledger.jsonl","calibration_ledger.jsonl"):
        p=target/name
        if not p.exists(): p.write_text("",encoding="utf-8")
    state={
        "schema":"MATRIX_PLAYER_SHOTS_V3_PROSPECTIVE_STATE_V1",
        "lane":"PLAYER_SHOTS_OVER_1_5",
        "status":"ACTIVE_WAITING_FIRST_PREMATCH_FREEZE" if eligible else "NO_GO_HISTORICAL_OOS",
        "prospective_freeze_allowed":eligible,
        "freeze_observation_count":0,
        "calibration_observation_count":0,
        "gates":{str(n):{"threshold":n,"status":"SEALED","observations_available":0,"remaining":n,"metrics_opened":False} for n in (30,50,100,200)},
        "metrics_policy":"SEALED_UNTIL_EACH_THRESHOLD_30_50_100_200",
        "model_selected_parameters_sha256":model.get("selected_parameters_sha256"),
        "role_source":"/fixtures/lineups",
        "parameter_tuning_allowed":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    (target/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return state


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--collect-lineups",action="store_true")
    args=parser.parse_args()
    out=Path("evidence/api_football/market_expansion/player_shots_v3")
    out.mkdir(parents=True,exist_ok=True)
    collection=collect_lineups(os.environ.get("API_FOOTBALL_KEY",""),out) if args.collect_lineups else json.loads((out/"lineup_cache_manifest.json").read_text())
    dataset=build_dataset(out)
    model=build_model(out)
    state=initialize_prospective(out,model)
    summary={
        "schema":"MATRIX_PLAYER_SHOTS_V3_RESOLUTION_V1",
        "lineup_collection_status":collection["status"],
        "fixture_count":collection["fixture_count"],
        "lineup_available_count":collection["lineup_available_count"],
        "network_calls_this_run":collection["network_calls_this_run"],
        "dataset_status":dataset["status"],
        "dataset_rows":dataset["row_count"],
        "train_rows":dataset["train_count"],
        "validation_rows":dataset["validation_count"],
        "model_status":model["status"],
        "historical_oos_gate_passed":bool(model.get("validation",{}).get("gate_passed")),
        "prospective_status":state["status"],
        "prospective_freeze_allowed":state["prospective_freeze_allowed"],
        "games_substitute_used":False,
        "role_source":"/fixtures/lineups",
        "real_money":"BLOCKED",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
