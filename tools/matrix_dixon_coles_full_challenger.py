from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib, json, math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from tools.api_football_retrospective_validation import (
    _load_json_bytes, _fixture, _team_view, _score_probs,
    MIN_TEAM_HISTORY, MAX_TEAM_HISTORY, MIN_GROUP_BASELINE_HISTORY,
)

RAW_DIR=Path("evidence/api_football/history/raw")
OUT=Path("evidence/api_football/model_validation/MATRIX_DIXON_COLES_FULL_CHALLENGER_V1.json")
FIT_FRACTION=0.60
VALIDATION_FRACTION=0.20
MIN_GROUP_FINALS=100
MIN_HOLDOUT_COMPARABLE=20
HALF_LIVES=(0,180,365)  # 0 = no decay
RHO_BOUND=0.20
RIDGE=0.01
IDENTITY_PENALTY=10.0
EPS=1e-12

def _tau(x:int,y:int,lam:float,mu:float,rho:float)->float:
    if x==0 and y==0:return 1-lam*mu*rho
    if x==0 and y==1:return 1+lam*rho
    if x==1 and y==0:return 1+mu*rho
    if x==1 and y==1:return 1-rho
    return 1.0

def _over25_from_lambdas(lam:float,mu:float)->float:
    s=lam+mu
    return 1-math.exp(-s)*(1+s+s*s/2.0)

def _safe_log_pois(k:int,lam:float)->float:
    return -lam+k*math.log(max(lam,EPS))-math.lgamma(k+1)

def _weights(matches:list[dict[str,Any]],half_life:int)->np.ndarray:
    if half_life<=0:return np.ones(len(matches),dtype=float)
    ref=datetime.fromisoformat(matches[-1]["kickoff_utc"])
    vals=[]
    for m in matches:
        dt=datetime.fromisoformat(m["kickoff_utc"])
        age=max(0.0,(ref-dt).total_seconds()/86400.0)
        vals.append(0.5**(age/float(half_life)))
    return np.asarray(vals,dtype=float)

def _fit_dc(matches:list[dict[str,Any]],half_life:int)->dict[str,Any]|None:
    teams=sorted({m["home_team_id"] for m in matches}|{m["away_team_id"] for m in matches})
    if len(teams)<4:return None
    idx={t:i for i,t in enumerate(teams)}
    n=len(teams)
    w=_weights(matches,half_life)
    def unpack(theta):
        att=theta[:n]; deff=theta[n:2*n]; home=theta[-2]; rho=theta[-1]
        return att,deff,home,rho
    def obj(theta):
        att,deff,home,rho=unpack(theta)
        total=0.0
        for wi,m in zip(w,matches):
            hi=idx[m["home_team_id"]]; ai=idx[m["away_team_id"]]
            lam=math.exp(float(home+att[hi]+deff[ai]))
            mu=math.exp(float(att[ai]+deff[hi]))
            if lam>8 or mu>8:return 1e9
            t=_tau(int(m["home_goals"]),int(m["away_goals"]),lam,mu,float(rho))
            if t<=EPS:return 1e9
            lp=_safe_log_pois(int(m["home_goals"]),lam)+_safe_log_pois(int(m["away_goals"]),mu)+math.log(t)
            total-=float(wi)*lp
        total+=RIDGE*float(np.sum(theta[:2*n]**2))
        total+=IDENTITY_PENALTY*(float(np.sum(att))**2+float(np.sum(deff))**2)
        return total
    x0=np.zeros(2*n+2,dtype=float)
    x0[-2]=0.15
    bounds=[(-2.0,2.0)]*(2*n)+[(-1.0,1.0),(-RHO_BOUND,RHO_BOUND)]
    res=minimize(obj,x0,method="L-BFGS-B",bounds=bounds,options={"maxiter":500,"ftol":1e-9})
    if not res.success or not np.isfinite(res.fun):return None
    att,deff,home,rho=unpack(res.x)
    return {
        "teams":teams,"index":idx,"attack":att.tolist(),"defense":deff.tolist(),
        "home_advantage":float(home),"rho":float(rho),
        "objective":float(res.fun),"optimizer_success":bool(res.success),
        "half_life_days":int(half_life),
    }

def _predict(model:dict[str,Any],m:dict[str,Any])->float|None:
    idx=model["index"]
    if m["home_team_id"] not in idx or m["away_team_id"] not in idx:return None
    hi=idx[m["home_team_id"]]; ai=idx[m["away_team_id"]]
    lam=math.exp(model["home_advantage"]+model["attack"][hi]+model["defense"][ai])
    mu=math.exp(model["attack"][ai]+model["defense"][hi])
    return _over25_from_lambdas(lam,mu)

def _score(rows,key):
    if not rows:return None
    b=ll=0.0
    for r in rows:
        p=min(max(float(r[key]),EPS),1-EPS); y=float(r["y"])
        b+=(p-y)**2
        ll+=-(y*math.log(p)+(1-y)*math.log(1-p))
    return {"n":len(rows),"brier":b/len(rows),"log_loss":ll/len(rows)}

def _current_walkforward(finals:list[dict[str,Any]])->dict[str,float]:
    prior=[]; by_team=defaultdict(list); out={}
    for target in finals:
        hid,aid=target["home_team_id"],target["away_team_id"]
        hh=by_team[hid][-MAX_TEAM_HISTORY:]; ah=by_team[aid][-MAX_TEAM_HISTORY:]
        if len(hh)>=MIN_TEAM_HISTORY and len(ah)>=MIN_TEAM_HISTORY and len(prior)>=MIN_GROUP_BASELINE_HISTORY:
            hgf=[_team_view(r,hid)[0] for r in hh]; hga=[_team_view(r,hid)[1] for r in hh]
            agf=[_team_view(r,aid)[0] for r in ah]; aga=[_team_view(r,aid)[1] for r in ah]
            hl=min(5.0,max(0.05,(sum(hgf)/len(hgf)+sum(aga)/len(aga))/2.0))
            al=min(5.0,max(0.05,(sum(agf)/len(agf)+sum(hga)/len(hga))/2.0))
            out[target["fixture_id"]]=_score_probs(hl,al)["over_2_5"]
        prior.append(target); by_team[hid].append(target); by_team[aid].append(target)
    return out

def _load_groups(raw_dir:Path):
    groups=[]
    for path in sorted(raw_dir.glob("league_*_season_*.bin")):
        payload=_load_json_bytes(path); response=payload.get("response")
        if not isinstance(response,list):continue
        finals=[f for raw in response for f in [_fixture(raw,source_path=path.as_posix())] if f is not None]
        finals.sort(key=lambda x:(x["kickoff_utc"],int(x["fixture_id"])))
        if len(finals)>=MIN_GROUP_FINALS:
            groups.append((path,finals))
    return groups

def build(raw_dir:Path=RAW_DIR)->dict[str,Any]:
    all_hold=[]; group_reports=[]; fitted_groups=0
    for path,finals in _load_groups(raw_dir):
        n=len(finals)
        fit_end=max(1,int(n*FIT_FRACTION))
        val_end=max(fit_end+1,int(n*(FIT_FRACTION+VALIDATION_FRACTION)))
        if val_end>=n:continue
        fit=finals[:fit_end]; val=finals[fit_end:val_end]; pre_hold=finals[:val_end]; hold=finals[val_end:]
        frozen=_current_walkforward(finals)
        candidate=[]
        for half in HALF_LIVES:
            model=_fit_dc(fit,half)
            if model is None:continue
            rr=[]
            for m in val:
                p=_predict(model,m)
                if p is None:continue
                rr.append({"p":p,"y":1.0 if m["home_goals"]+m["away_goals"]>=3 else 0.0})
            sc=_score(rr,"p")
            if sc:
                candidate.append({"half_life_days":half,"validation":sc,"rho":model["rho"]})
        if not candidate:continue
        selected=min(candidate,key=lambda x:(x["validation"]["brier"],x["validation"]["log_loss"],x["half_life_days"]))
        final_model=_fit_dc(pre_hold,int(selected["half_life_days"]))
        if final_model is None:continue
        local=[]
        for m in hold:
            dc=_predict(final_model,m); fr=frozen.get(m["fixture_id"])
            if dc is None or fr is None:continue
            local.append({
                "fixture_id":m["fixture_id"],"kickoff_utc":m["kickoff_utc"],
                "y":1.0 if m["home_goals"]+m["away_goals"]>=3 else 0.0,
                "dc":dc,"frozen":fr,
            })
        if len(local)<MIN_HOLDOUT_COMPARABLE:continue
        fitted_groups+=1; all_hold.extend(local)
        group_reports.append({
            "source_path":path.as_posix(),"final_count":n,"fit_n":len(fit),"validation_n":len(val),"holdout_n":len(local),
            "selected_half_life_days":selected["half_life_days"],"validation_candidates":candidate,
            "final_rho":final_model["rho"],"optimizer_success":final_model["optimizer_success"],
            "holdout_dc":_score(local,"dc"),"holdout_frozen":_score(local,"frozen"),
        })
    dc=_score(all_hold,"dc"); fr=_score(all_hold,"frozen")
    if dc is None or fr is None:raise ValueError("NO_COMPARABLE_HOLDOUT_ROWS")
    db=dc["brier"]-fr["brier"]; dl=dc["log_loss"]-fr["log_loss"]
    superior=db<0 and dl<0
    out={
        "schema":"MATRIX_DIXON_COLES_FULL_CHALLENGER_V1",
        "evaluation_kind":"LEAGUE_SEASON_CHRONOLOGICAL_60_20_20_RESEARCH_ONLY",
        "eligible_group_count":len(_load_groups(raw_dir)),"fitted_group_count":fitted_groups,
        "holdout_comparable_n":len(all_hold),
        "pre_registered_half_lives_days":list(HALF_LIVES),"minimum_holdout_comparable_per_group":MIN_HOLDOUT_COMPARABLE,
        "selection_rule":"MIN_VALIDATION_BRIER_THEN_LOGLOSS_THEN_SHORTEST_HALF_LIFE",
        "aggregate_holdout":{"dixon_coles":dc,"frozen_poisson":fr,
            "delta_dc_minus_frozen":{"brier":db,"log_loss":dl}},
        "holdout_beats_frozen_both_metrics":superior,
        "adjudication":"RESEARCH_CANDIDATE_ONLY_REQUIRES_PROSPECTIVE_VALIDATION" if superior else "NO_PROMOTION_DIXON_COLES_NOT_SUPERIOR_ON_HOLDOUT",
        "group_reports":group_reports,
        "method_note":"Regularized Dixon-Coles attack/defence/home-advantage/rho fit. Half-life selected on validation only; selected model refit on pre-holdout 80% and frozen before final 20%.",
        "governance":{
            "research_only":True,"production_engine_modified":False,"p_matrix_modified":False,
            "telegram_modified":False,"holdout_used_for_parameter_selection":False,
            "odds_used_to_generate_probability":False,"automatic_wagering":False,"real_money":"BLOCKED"
        }
    }
    out["artifact_sha256"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return out

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
        "status":"PASS","fitted_group_count":out["fitted_group_count"],
        "holdout_comparable_n":out["holdout_comparable_n"],
        "holdout_beats_frozen_both_metrics":out["holdout_beats_frozen_both_metrics"],
        "artifact_sha256":out["artifact_sha256"],"real_money":out["governance"]["real_money"]
    },sort_keys=True))

if __name__=="__main__":main()
