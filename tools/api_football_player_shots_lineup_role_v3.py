from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from math import exp, floor, log
from pathlib import Path
from typing import Any, Mapping
import requests

from tools.api_football_player_shots_expected_minutes_v2 import _load_fixture_sources

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20.0
MIN_OVERALL_HISTORY=5
MIN_ROLE_HISTORY=3
MAX_OVERALL_HISTORY=20
MAX_ROLE_HISTORY=10
MIN_TRAIN=200
MIN_VALIDATION=50
EPS=1e-15

def _utc(value:object)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)

def _roles_with_conflicts(payload:Mapping[str,Any])->tuple[dict[str,str],list[str]]:
    out={}
    conflicts=set()
    for tr in payload.get("response") or []:
        if not isinstance(tr,Mapping): continue
        for key,role in (("startXI","STARTER"),("substitutes","SUBSTITUTE")):
            for item in tr.get(key) or []:
                p=item.get("player") if isinstance(item,Mapping) and isinstance(item.get("player"),Mapping) else {}
                pid=str(p.get("id") or "")
                if not pid or pid in conflicts: continue
                if pid in out and out[pid]!=role:
                    conflicts.add(pid)
                    out.pop(pid,None)
                    continue
                out[pid]=role
    return out,sorted(conflicts)

def _roles(payload:Mapping[str,Any])->dict[str,str]:
    roles,_=_roles_with_conflicts(payload)
    return roles

def _stats(path:Path)->list[dict[str,Any]]:
    try: payload=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeDecodeError,json.JSONDecodeError): return []
    out=[]
    for tr in payload.get("response") or []:
        if not isinstance(tr,Mapping): continue
        team=tr.get("team") if isinstance(tr.get("team"),Mapping) else {}
        for pr in tr.get("players") or []:
            if not isinstance(pr,Mapping): continue
            player=pr.get("player") if isinstance(pr.get("player"),Mapping) else {}
            pid=str(player.get("id") or "")
            if not pid: continue
            for stat in pr.get("statistics") or []:
                if not isinstance(stat,Mapping): continue
                games=stat.get("games") if isinstance(stat.get("games"),Mapping) else {}
                shots=stat.get("shots") if isinstance(stat.get("shots"),Mapping) else {}
                minutes=games.get("minutes"); count=shots.get("total")
                if minutes is None or count is None: continue
                try: mf=float(minutes); sf=float(count)
                except (TypeError,ValueError): continue
                if mf<=0 or sf<0: continue
                out.append({"player_id":pid,"player_name":player.get("name"),"team_id":str(team.get("id") or ""),"team_name":team.get("name"),"minutes":mf,"shots":sf})
                break
    return out

def _mean(xs:list[float])->float:
    return sum(xs)/len(xs)

def _rate(rows:list[dict[str,Any]])->float:
    mins=sum(float(x["minutes"]) for x in rows)
    return 90.0*sum(float(x["shots"]) for x in rows)/mins if mins>0 else 0.0

def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)

def _poisson_over(mu:float,line:float)->float:
    mu=max(0.01,float(mu)); cut=int(floor(line))
    term=exp(-mu); cdf=term
    for k in range(1,cut+1):
        term*=mu/k; cdf+=term
    return _clip(1-cdf)

def _metrics(ys:list[int],ps:list[float])->dict[str,float]:
    b=ll=0.0; bins=[[] for _ in range(5)]
    for y,p0 in zip(ys,ps):
        p=_clip(p0); b+=(p-y)**2; ll+=-(y*log(p)+(1-y)*log(1-p))
        bins[min(4,int(p*5))].append((y,p))
    n=len(ys); ece=0.0; mx=0.0
    for bucket in bins:
        if not bucket: continue
        o=sum(y for y,_ in bucket)/len(bucket); q=sum(p for _,p in bucket)/len(bucket)
        er=abs(o-q); ece+=len(bucket)/n*er; mx=max(mx,er)
    return {"sample_size":n,"brier_score":b/n,"log_loss":ll/n,"ece_5bin":ece,"max_calibration_error_5bin":mx}

def _mu_role(row:Mapping[str,Any],alpha:float)->float:
    rate=(1-alpha)*float(row["role_prior_shots_per90"])+alpha*float(row["role_recent3_shots_per90"])
    return max(0.01,rate*min(90.0,max(1.0,float(row["expected_minutes_pit"])))/90.0)

def _mu_agnostic(row:Mapping[str,Any])->float:
    return max(0.01,float(row["overall_prior_shots_per90"])*min(90.0,max(1.0,float(row["prior_mean_minutes"])))/90.0)

def _internal_folds(rows:list[dict[str,Any]]):
    n=len(rows); initial=max(140,int(n*0.65)); rem=n-initial
    if rem<30: raise ValueError("INSUFFICIENT_INTERNAL_OOS")
    widths=[rem//3,rem//3]; widths.append(rem-sum(widths))
    pos=initial; out=[]
    for w in widths:
        out.append((rows[:pos],rows[pos:pos+w])); pos+=w
    return out

def _fetch_lineups(fixtures:list[dict[str,Any]],key:str,out_dir:Path)->tuple[dict[str,dict[str,str]],dict[str,Any]]:
    cache=out_dir/"raw_lineups"; cache.mkdir(parents=True,exist_ok=True)
    session=requests.Session(); mappings={}; calls=0; missing=0
    records=[]; role_conflict_player_rows=0; conflict_fixture_count=0
    for f in fixtures:
        fid=str(f["fixture_id"]); p=cache/f"fixture_{fid}_lineups.json"
        if p.exists():
            raw=p.read_bytes(); payload=json.loads(raw.decode("utf-8"))
        else:
            resp=session.get(BASE_URL+"/fixtures/lineups",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
            calls+=1; raw=bytes(resp.content)
            try: payload=resp.json()
            except ValueError: payload={}
            p.write_bytes(raw)
        if isinstance(payload,Mapping):
            rolemap,conflicts=_roles_with_conflicts(payload)
        else:
            rolemap,conflicts={},[]
        if not rolemap: missing+=1
        if conflicts:
            conflict_fixture_count+=1
            role_conflict_player_rows+=len(conflicts)
        mappings[fid]=rolemap
        records.append({
            "fixture_id":fid,"role_count":len(rolemap),
            "role_conflict_player_ids_quarantined":conflicts,
            "role_conflict_count":len(conflicts),
            "raw_sha256":hashlib.sha256(p.read_bytes()).hexdigest()
        })
    return mappings,{
        "provider_network_calls":calls,"fixture_count":len(fixtures),
        "fixtures_without_lineup":missing,
        "lineup_role_conflict_fixture_count":conflict_fixture_count,
        "lineup_role_conflict_player_rows_quarantined":role_conflict_player_rows,
        "conflict_policy":"QUARANTINE_AMBIGUOUS_PLAYER_ROLE_MISSING_NOT_ZERO",
        "records":records
    }

def build_dataset(api_key:str,out_dir:Path)->dict[str,Any]:
    fixtures,dupes=_load_fixture_sources()
    if not fixtures: raise ValueError("NO_FIXTURE_SOURCES")
    rolemaps,source_audit=_fetch_lineups(fixtures,api_key,out_dir)
    history=defaultdict(list); rows=[]; missing_roles=0; insufficient_overall=0; insufficient_role=0
    for fixture in fixtures:
        fid=str(fixture["fixture_id"]); roles=rolemaps.get(fid,{})
        apps=_stats(Path(fixture["raw_players_path"]))
        pending=[]
        for app in apps:
            role=roles.get(app["player_id"])
            if role is None:
                missing_roles+=1; continue
            prior=history[app["player_id"]][-MAX_OVERALL_HISTORY:]
            if len(prior)<MIN_OVERALL_HISTORY:
                insufficient_overall+=1
            else:
                role_prior=[x for x in prior if x["role"]==role][-MAX_ROLE_HISTORY:]
                if len(role_prior)<MIN_ROLE_HISTORY:
                    insufficient_role+=1
                else:
                    last5=prior[-5:]; recent_role=role_prior[-3:]
                    rows.append({
                        "fixture_id":fid,"kickoff_utc":fixture["kickoff_utc"],"league_id":fixture["league_id"],"season":fixture["season"],
                        "player_id":app["player_id"],"player_name":app["player_name"],"team_id":app["team_id"],"team_name":app["team_name"],
                        "lineup_role":role,"historical_role_source":"/fixtures/lineups","prospective_role_source":"/fixtures/lineups",
                        "prior_appearance_count":len(prior),"prior_role_appearance_count":len(role_prior),
                        "prior_mean_minutes":_mean([float(x["minutes"]) for x in prior]),
                        "last5_mean_minutes":_mean([float(x["minutes"]) for x in last5]),
                        "overall_prior_shots_per90":_rate(prior),
                        "role_prior_shots_per90":_rate(role_prior),
                        "role_recent3_shots_per90":_rate(recent_role),
                        "expected_minutes_pit":_mean([float(x["minutes"]) for x in role_prior]),
                        "expected_minutes_source":"MEAN_PRIOR_SAME_LINEUP_ROLE_MINUTES_ONLY",
                        "target_shots":float(app["shots"]),
                        "current_match_minutes_postsettlement_audit_only":float(app["minutes"]),
                        "current_match_minutes_used_as_feature":False,
                        "same_match_shots_used_in_features":False,
                    })
            pending.append({**app,"role":role})
        for app in pending:
            history[app["player_id"]].append({"fixture_id":fid,"kickoff_utc":fixture["kickoff_utc"],"role":app["role"],"minutes":app["minutes"],"shots":app["shots"]})
    rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"]),int(r["player_id"])))
    split=len(rows)-MIN_VALIDATION if len(rows)>=MIN_TRAIN+MIN_VALIDATION else 0
    for i,r in enumerate(rows): r["split"]="TRAIN" if i<split else "VALIDATION"
    dataset=out_dir/"player_shots_lineup_role_pit.jsonl"
    dataset.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    manifest={
        "schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_PIT_V3","generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fixture_count":len(fixtures),"duplicate_fixture_ids_quarantined":dupes,"row_count":len(rows),"train_count":split,"validation_count":len(rows)-split,
        "historical_role_source":"/fixtures/lineups","prospective_role_source":"/fixtures/lineups","same_role_semantics_by_construction":True,
        "source_audit":source_audit,"missing_role_for_player_stat_rows":missing_roles,"insufficient_overall_history_count":insufficient_overall,"insufficient_same_role_history_count":insufficient_role,
        "current_match_minutes_used_as_feature":False,"same_match_target_used_in_features":False,"odds_used_to_generate_probability":False,"real_money":"BLOCKED"
    }
    (out_dir/"dataset_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest

def build_model(out_dir:Path)->dict[str,Any]:
    rows=[json.loads(x) for x in (out_dir/"player_shots_lineup_role_pit.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    train=[r for r in rows if r["split"]=="TRAIN"]; val=[r for r in rows if r["split"]=="VALIDATION"]
    if len(train)<MIN_TRAIN or len(val)<MIN_VALIDATION:
        return {"schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_MODEL_V3","status":"SEALED_INSUFFICIENT_OOS","train_count":len(train),"validation_count":len(val),"prospective_eligible":False,"real_money":"BLOCKED"}
    line=1.5; trials=[]
    for alpha in (0.0,0.25,0.5,0.75,1.0):
        ys=[]; ps=[]
        for fit,test in _internal_folds(train):
            ys.extend([int(float(r["target_shots"])>line) for r in test])
            ps.extend([_poisson_over(_mu_role(r,alpha),line) for r in test])
        trials.append({"alpha_recent_rate":alpha,"internal_validation":_metrics(ys,ps)})
    trials.sort(key=lambda x:(x["internal_validation"]["log_loss"],x["internal_validation"]["brier_score"]))
    selected=trials[0]
    ys=[int(float(r["target_shots"])>line) for r in val]
    role_ps=[_poisson_over(_mu_role(r,float(selected["alpha_recent_rate"])),line) for r in val]
    agn_ps=[_poisson_over(_mu_agnostic(r),line) for r in val]
    cm=_metrics(ys,role_ps); bm=_metrics(ys,agn_ps)
    pass_gate=(cm["brier_score"]<bm["brier_score"] and cm["log_loss"]<bm["log_loss"] and cm["ece_5bin"]<=0.10 and cm["max_calibration_error_5bin"]<=0.20)
    frozen={"evaluation_line":line,"alpha_recent_rate":selected["alpha_recent_rate"],"expected_minutes_method":"MEAN_PRIOR_SAME_LINEUP_ROLE_MINUTES_ONLY","historical_role_source":"/fixtures/lineups","prospective_role_source":"/fixtures/lineups","minimum_same_role_history":MIN_ROLE_HISTORY}
    return {
        "schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_MODEL_V3","lane":"PLAYER_SHOTS","candidate":"lineup_role_expected_minutes_v3",
        "source_dataset":str(out_dir/"player_shots_lineup_role_pit.jsonl"),"source_dataset_sha256":hashlib.sha256((out_dir/"player_shots_lineup_role_pit.jsonl").read_bytes()).hexdigest(),
        "row_count":len(rows),"train_count":len(train),"validation_count":len(val),"evaluation_line":line,
        "internal_selection":{"trial_count":len(trials),"selected":selected,"final_validation_used_for_selection":False},
        "selected_parameters":frozen,"selected_parameters_sha256":hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "validation":{"challenger_v3":cm,"role_agnostic_same_rows":bm,"delta_brier":cm["brier_score"]-bm["brier_score"],"delta_log_loss":cm["log_loss"]-bm["log_loss"],"gate_passed":pass_gate},
        "historical_and_prospective_role_source_identical":True,"prematch_lineup_source_certified":True,
        "expected_minutes_pit_prospective_certified":pass_gate,"prospective_freeze_allowed":pass_gate,
        "status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION_V3" if pass_gate else "REJECTED_HISTORICAL_OOS_V3",
        "prospective_gates":[30,50,100,200] if pass_gate else [],
        "validation_used_for_parameter_tuning":False,"protected_final_holdout_used":False,"odds_used_to_generate_probability":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main()->None:
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key: raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    out=Path("evidence/api_football/market_expansion/player_shots_lineup_role_v3"); out.mkdir(parents=True,exist_ok=True)
    dataset=build_dataset(key,out)
    model=build_model(out)
    (out/"model.json").write_text(json.dumps(model,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    summary={"schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_V3_SUMMARY","dataset":{"rows":dataset["row_count"],"train":dataset["train_count"],"validation":dataset["validation_count"],"network_calls":dataset["source_audit"]["provider_network_calls"],"fixtures_without_lineup":dataset["source_audit"]["fixtures_without_lineup"]},"model_status":model["status"],"prospective_eligible":model.get("prospective_freeze_allowed",False),"validation":model.get("validation"),"automatic_wagering":False,"real_money":"BLOCKED"}
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))

if __name__=="__main__":
    main()
