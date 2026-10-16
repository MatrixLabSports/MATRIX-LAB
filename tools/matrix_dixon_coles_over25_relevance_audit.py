from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from typing import Any

SOURCE=Path("evidence/api_football/model_validation/retrospective_predictions_chunks/chunk_0001.json")
OUT=Path("evidence/api_football/model_validation/MATRIX_DIXON_COLES_OVER25_RELEVANCE_AUDIT_V1.json")
RHO_GRID=(-0.20,-0.15,-0.10,-0.05,0.0,0.05,0.10,0.15,0.20)

def _sha_bytes(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _pois(k:int,lam:float)->float:
    return math.exp(-lam)*(lam**k)/math.factorial(k)

def tau(x:int,y:int,lam:float,mu:float,rho:float)->float:
    if x==0 and y==0:return 1-lam*mu*rho
    if x==0 and y==1:return 1+lam*rho
    if x==1 and y==0:return 1+mu*rho
    if x==1 and y==1:return 1-rho
    return 1.0

def audit_row(row:dict[str,Any],rho:float)->dict[str,float]:
    lam=float(row["expected_home_goals"]); mu=float(row["expected_away_goals"])
    cells=[(0,0),(0,1),(1,0),(1,1)]
    base=sum(_pois(x,lam)*_pois(y,mu) for x,y in cells)
    corrected=sum(tau(x,y,lam,mu,rho)*_pois(x,lam)*_pois(y,mu) for x,y in cells)
    delta=corrected-base
    s=lam+mu
    p_over=1-math.exp(-s)*(1+s+s*s/2)
    # Because tau differs from 1 only in four Under-2.5 cells and their net mass delta is zero.
    p_over_dc=p_over/(1+delta)
    return {"mass_delta":delta,"poisson_over25":p_over,"dc_over25":p_over_dc,"over25_delta":p_over_dc-p_over}

def build(rows:list[dict[str,Any]])->dict[str,Any]:
    results=[]
    max_mass=max_over=0.0
    invalid_tau=0
    for rho in RHO_GRID:
        local_mass=local_over=0.0
        for row in rows:
            lam=float(row["expected_home_goals"]); mu=float(row["expected_away_goals"])
            if any(tau(x,y,lam,mu,rho)<0 for x,y in ((0,0),(0,1),(1,0),(1,1))):
                invalid_tau+=1
                continue
            a=audit_row(row,rho)
            local_mass=max(local_mass,abs(a["mass_delta"]))
            local_over=max(local_over,abs(a["over25_delta"]))
        max_mass=max(max_mass,local_mass); max_over=max(max_over,local_over)
        results.append({"rho":rho,"max_abs_probability_mass_delta":local_mass,"max_abs_over25_delta":local_over})
    out={
      "schema":"MATRIX_DIXON_COLES_OVER25_RELEVANCE_AUDIT_V1",
      "source_path":SOURCE.as_posix(),"source_sha256":_sha_bytes(SOURCE) if SOURCE.exists() else None,
      "row_count":len(rows),"rho_grid":list(RHO_GRID),"rho_row_combinations_with_invalid_tau":invalid_tau,
      "results":results,"max_abs_probability_mass_delta":max_mass,"max_abs_over25_delta":max_over,
      "finding":"LOW_SCORE_TAU_WITH_FIXED_LAMBDAS_DOES_NOT_CHANGE_OVER25",
      "actionable_next_challenger":"REFIT_LAMBDAS_WITH_TIME_DECAY_AND_DIXON_COLES_LIKELIHOOD_RESEARCH_ONLY",
      "production_engine_modified":False,"parameter_tuning_allowed":False,"odds_used_to_generate_probability":False,
      "automatic_wagering":False,"real_money":"BLOCKED"
    }
    raw=json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    out["artifact_sha256"]=hashlib.sha256(raw).hexdigest()
    return out

def main():
    rows=json.loads(SOURCE.read_text())
    if not isinstance(rows,list): raise SystemExit("SOURCE_NOT_LIST")
    out=build(rows)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"PASS","rows":out["row_count"],"max_abs_over25_delta":out["max_abs_over25_delta"],"artifact_sha256":out["artifact_sha256"],"real_money":out["real_money"]},sort_keys=True))

if __name__=="__main__":main()
