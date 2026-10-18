from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib, json, math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from tools.api_football_retrospective_validation import (
    _load_json_bytes, _fixture, build_retrospective_walk_forward
)

RAW_DIR=Path("evidence/api_football/history/raw")
OUT=Path("evidence/api_football/model_validation/MATRIX_DIXON_COLES_FULL_OVER25_CHALLENGER_V1.json")
DEV_FRACTION=0.70
MIN_GROUP_FINALS=40
RHO_BOUNDS=(-0.20,0.20)
PARAM_BOUND=2.5
HOME_BOUND=1.5
RIDGE=1e-4
EPS=1e-12

def _tau(x:int,y:int,lam:float,mu:float,rho:float)->float:
    if x==0 and y==0: return 1-lam*mu*rho
    if x==0 and y==1: return 1+lam*rho
    if x==1 and y==0: return 1+mu*rho
    if x==1 and y==1: return 1-rho
    return 1.0

def _pois_logpmf(k:int,lam:float)->float:
    return -lam + k*math.log(max(lam,EPS)) - math.lgamma(k+1)

def _over25(lam:float,mu:float)->float:
    s=lam+mu
    return 1-math.exp(-s)*(1+s+s*s/2)

def _brier(rows,key):
    return sum((float(r[key])-float(r["y"]))**2 for r in rows)/len(rows)

def _logloss(rows,key):
    total=0.0
    for r in rows:
        p=min(max(float(r[key]),EPS),1-EPS); y=float(r["y"])
        total+=-(y*math.log(p)+(1-y)*math.log(1-p))
    return total/len(rows)

def _fit_dc(dev:list[dict[str,Any]])->dict[str,Any] | None:
    teams=sorted({r["home_team_id"] for r in dev}|{r["away_team_id"] for r in dev})
    if len(teams)<4: return None
    idx={t:i for i,t in enumerate(teams)}
    n=len(teams)
    # attacks n-1 (last fixed at zero), defenses n, home advantage, rho
    dim=(n-1)+n+2
    x0=np.zeros(dim,dtype=float)
    x0[-2]=math.log(max(sum(r["home_goals"] for r in dev)/len(dev),0.2)) - math.log(max(sum(r["away_goals"] for r in dev)/len(dev),0.2))
    def unpack(x):
        attack=np.zeros(n,dtype=float); attack[:n-1]=x[:n-1]
        attack-=attack.mean()
        defense=x[n-1:n-1+n]
        home=float(x[-2]); rho=float(x[-1])
        return attack,defense,home,rho
    def objective(x):
        attack,defense,home,rho=unpack(x)
        loss=0.0
        for r in dev:
            hi,ai=idx[r["home_team_id"]],idx[r["away_team_id"]]
            lam=math.exp(max(-5,min(5,home+attack[hi]+defense[ai])))
            mu=math.exp(max(-5,min(5,attack[ai]+defense[hi])))
            t=_tau(int(r["home_goals"]),int(r["away_goals"]),lam,mu,rho)
            if t<=0 or not math.isfinite(t): return 1e12
            loss-=(_pois_logpmf(int(r["home_goals"]),lam)+_pois_logpmf(int(r["away_goals"]),mu)+math.log(t))
        loss+=RIDGE*float(np.dot(x[:-1],x[:-1]))
        return loss
    bounds=[(-PARAM_BOUND,PARAM_BOUND)]*((n-1)+n)+[(-HOME_BOUND,HOME_BOUND),RHO_BOUNDS]
    res=minimize(objective,x0,method="L-BFGS-B",bounds=bounds,options={"maxiter":800,"ftol":1e-10})
    if not res.success or not math.isfinite(float(res.fun)): return None
    attack,defense,home,rho=unpack(res.x)
    return {"teams":teams,"idx":idx,"attack":attack,"defense":defense,"home":home,"rho":rho,"nll":float(res.fun),"iterations":int(res.nit)}

def build(raw_dir:Path=RAW_DIR)->dict[str,Any]:
    reference=build_retrospective_walk_forward(raw_dir)
    ref={str(r["fixture_id"]):r for r in reference["predictions"]}
    eval_rows=[]; groups=[]; fit_failures=0
    for path in sorted(raw_dir.glob("league_*_season_*.bin")):
        payload=_load_json_bytes(path); response=payload.get("response")
        if not isinstance(response,list): continue
        finals=[f for raw in response for f in [_fixture(raw,source_path=path.as_posix())] if f is not None]
        finals.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
        if len(finals)<MIN_GROUP_FINALS: continue
        cut=max(20,min(len(finals)-1,int(len(finals)*DEV_FRACTION)))
        dev,hold=finals[:cut],finals[cut:]
        fit=_fit_dc(dev)
        if fit is None:
            fit_failures+=1; continue
        seen=set(fit["teams"]); scored=0
        for r in hold:
            if r["home_team_id"] not in seen or r["away_team_id"] not in seen: continue
            rr=ref.get(str(r["fixture_id"]))
            if rr is None: continue
            hi,ai=fit["idx"][r["home_team_id"]],fit["idx"][r["away_team_id"]]
            lam=math.exp(max(-5,min(5,fit["home"]+fit["attack"][hi]+fit["defense"][ai])))
            mu=math.exp(max(-5,min(5,fit["attack"][ai]+fit["defense"][hi])))
            pdc=_over25(lam,mu)
            pref=float(rr["poisson"]["over_2_5"])
            eval_rows.append({
                "fixture_id":str(r["fixture_id"]),"kickoff_utc":r["kickoff_utc"],
                "league_id":r["league_id"],"season":r["season"],
                "y":1.0 if int(r["home_goals"])+int(r["away_goals"])>=3 else 0.0,
                "frozen_poisson":pref,"dixon_coles":pdc,
                "dc_home_lambda":lam,"dc_away_lambda":mu,"rho":fit["rho"],
            }); scored+=1
        groups.append({
            "source_path":path.as_posix(),"final_count":len(finals),"development_n":len(dev),
            "holdout_n":len(hold),"scored_holdout_n":scored,"team_count":len(fit["teams"]),
            "rho":fit["rho"],"home_advantage":fit["home"],"nll":fit["nll"],"iterations":fit["iterations"],
        })
    eval_rows.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    if not eval_rows: raise ValueError("NO_EVALUATION_ROWS")
    metrics={
        "holdout":{
            "n":len(eval_rows),
            "frozen_brier":_brier(eval_rows,"frozen_poisson"),
            "frozen_log_loss":_logloss(eval_rows,"frozen_poisson"),
            "dixon_coles_brier":_brier(eval_rows,"dixon_coles"),
            "dixon_coles_log_loss":_logloss(eval_rows,"dixon_coles"),
        }
    }
    h=metrics["holdout"]
    db=h["dixon_coles_brier"]-h["frozen_brier"]
    dl=h["dixon_coles_log_loss"]-h["frozen_log_loss"]
    beats=db<0 and dl<0
    out={
        "schema":"MATRIX_DIXON_COLES_FULL_OVER25_CHALLENGER_V1",
        "evaluation_kind":"LEAGUE_SEASON_CHRONOLOGICAL_70_30_HOLDOUT_RESEARCH_ONLY",
        "literature_basis":{
            "dixon_coles_1997":"Poisson regression with low-score dependence correction and dynamic team strength context",
            "benter_1994":"Fundamental model and public probability should remain separable before any second-stage combination",
        },
        "development_fraction":DEV_FRACTION,"minimum_group_finals":MIN_GROUP_FINALS,
        "rho_bounds":list(RHO_BOUNDS),"ridge":RIDGE,
        "group_fit_count":len(groups),"fit_failure_count":fit_failures,
        "holdout_row_count":len(eval_rows),"metrics":metrics,
        "holdout_delta_dc_minus_frozen":{"brier":db,"log_loss":dl},
        "holdout_beats_frozen_both_metrics":beats,
        "adjudication":"CANDIDATE_FOR_PROSPECTIVE_SHADOW_ONLY" if beats else "NO_PROMOTION_DIXON_COLES_NOT_SUPERIOR_ON_HOLDOUT",
        "groups":groups,
        "governance":{
            "research_only":True,"production_engine_modified":False,"p_matrix_modified":False,
            "telegram_modified":False,"holdout_used_for_parameter_selection":False,
            "odds_used_to_generate_probability":False,"automatic_wagering":False,"real_money":"BLOCKED",
            "second_stage_market_fusion_enabled":False,
        }
    }
    out["artifact_sha256"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return out

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
        "status":"PASS","holdout_row_count":out["holdout_row_count"],
        "delta_brier":out["holdout_delta_dc_minus_frozen"]["brier"],
        "delta_log_loss":out["holdout_delta_dc_minus_frozen"]["log_loss"],
        "adjudication":out["adjudication"],"artifact_sha256":out["artifact_sha256"],
        "real_money":out["governance"]["real_money"]
    },sort_keys=True))

if __name__=="__main__": main()
