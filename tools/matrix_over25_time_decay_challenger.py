from __future__ import annotations
from collections import defaultdict
from datetime import datetime
import hashlib, json, math
from pathlib import Path
from typing import Any

from tools.api_football_retrospective_validation import (
    _load_json_bytes,_fixture,_team_view,_score_probs,
    MIN_TEAM_HISTORY,MAX_TEAM_HISTORY,MIN_GROUP_BASELINE_HISTORY
)

RAW_DIR=Path("evidence/api_football/history/raw")
OUT=Path("evidence/api_football/model_validation/MATRIX_OVER25_TIME_DECAY_CHALLENGER_V1.json")
HALF_LIVES=(30,60,90,180)
DEV_FRACTION=0.70
EPS=1e-15

def _wmean(values:list[tuple[float,float]])->float:
    sw=sum(w for _,w in values)
    if sw<=0: raise ValueError("WEIGHT_SUM_ZERO")
    return sum(v*w for v,w in values)/sw

def _brier(rows,key):
    return sum((float(r[key])-float(r["y"]))**2 for r in rows)/len(rows)

def _logloss(rows,key):
    s=0.0
    for r in rows:
        p=min(max(float(r[key]),EPS),1-EPS); y=float(r["y"])
        s+=-(y*math.log(p)+(1-y)*math.log(1-p))
    return s/len(rows)

def _weighted_lambda(history,team_id,target_dt,kind,half_life):
    vals=[]
    for row in history:
        gf,ga=_team_view(row,team_id)
        age=max(0.0,(target_dt-datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z","+00:00"))).total_seconds()/86400.0)
        w=0.5**(age/half_life)
        vals.append(((gf if kind=="gf" else ga),w))
    return _wmean(vals)

def build(raw_dir:Path=RAW_DIR)->dict[str,Any]:
    rows=[]
    for path in sorted(raw_dir.glob("league_*_season_*.bin")):
        payload=_load_json_bytes(path)
        response=payload.get("response")
        if not isinstance(response,list): continue
        finals=[f for raw in response for f in [_fixture(raw,source_path=path.as_posix())] if f is not None]
        finals.sort(key=lambda x:(x["kickoff_utc"],int(x["fixture_id"])))
        prior=[]; by_team=defaultdict(list)
        for target in finals:
            hid,aid=target["home_team_id"],target["away_team_id"]
            hh=by_team[hid][-MAX_TEAM_HISTORY:]; ah=by_team[aid][-MAX_TEAM_HISTORY:]
            if len(hh)>=MIN_TEAM_HISTORY and len(ah)>=MIN_TEAM_HISTORY and len(prior)>=MIN_GROUP_BASELINE_HISTORY:
                tdt=datetime.fromisoformat(target["kickoff_utc"])
                # Frozen current reference: simple means over last <=20.
                hgf=[_team_view(r,hid)[0] for r in hh]; hga=[_team_view(r,hid)[1] for r in hh]
                agf=[_team_view(r,aid)[0] for r in ah]; aga=[_team_view(r,aid)[1] for r in ah]
                hl=min(5.0,max(0.05,(sum(hgf)/len(hgf)+sum(aga)/len(aga))/2))
                al=min(5.0,max(0.05,(sum(agf)/len(agf)+sum(hga)/len(hga))/2))
                frozen=_score_probs(hl,al)["over_2_5"]
                rec={"fixture_id":target["fixture_id"],"kickoff_utc":target["kickoff_utc"],"y":1.0 if target["home_goals"]+target["away_goals"]>=3 else 0.0,"frozen":frozen}
                for half in HALF_LIVES:
                    whgf=_weighted_lambda(hh,hid,tdt,"gf",half)
                    whga=_weighted_lambda(hh,hid,tdt,"ga",half)
                    wagf=_weighted_lambda(ah,aid,tdt,"gf",half)
                    waga=_weighted_lambda(ah,aid,tdt,"ga",half)
                    dhl=min(5.0,max(0.05,(whgf+waga)/2))
                    dal=min(5.0,max(0.05,(wagf+whga)/2))
                    rec[f"hl_{half}"]=_score_probs(dhl,dal)["over_2_5"]
                rows.append(rec)
            prior.append(target); by_team[hid].append(target); by_team[aid].append(target)
    rows.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    cut=max(1,min(len(rows)-1,int(len(rows)*DEV_FRACTION)))
    dev,hold=rows[:cut],rows[cut:]
    candidates=[]
    for half in HALF_LIVES:
        key=f"hl_{half}"
        candidates.append({"half_life_days":half,"dev_brier":_brier(dev,key),"dev_log_loss":_logloss(dev,key)})
    selected=min(candidates,key=lambda x:(x["dev_brier"],x["dev_log_loss"],x["half_life_days"]))
    sk=f'hl_{selected["half_life_days"]}'
    metrics={
        "development":{"n":len(dev),"frozen_brier":_brier(dev,"frozen"),"frozen_log_loss":_logloss(dev,"frozen"),"selected_brier":_brier(dev,sk),"selected_log_loss":_logloss(dev,sk)},
        "holdout":{"n":len(hold),"frozen_brier":_brier(hold,"frozen"),"frozen_log_loss":_logloss(hold,"frozen"),"selected_brier":_brier(hold,sk),"selected_log_loss":_logloss(hold,sk)},
    }
    hb=metrics["holdout"]
    improved=hb["selected_brier"]<hb["frozen_brier"] and hb["selected_log_loss"]<hb["frozen_log_loss"]
    out={
        "schema":"MATRIX_OVER25_TIME_DECAY_CHALLENGER_V1",
        "evaluation_kind":"RETROSPECTIVE_CHRONOLOGICAL_DEVELOPMENT_HOLDOUT_RESEARCH_ONLY",
        "row_count":len(rows),"development_fraction":DEV_FRACTION,
        "pre_registered_half_lives_days":list(HALF_LIVES),
        "selection_rule":"MIN_DEVELOPMENT_BRIER_THEN_LOGLOSS_THEN_SHORTEST_HALF_LIFE",
        "selected_half_life_days":selected["half_life_days"],
        "candidate_development_metrics":candidates,
        "metrics":metrics,
        "holdout_delta_selected_minus_frozen":{
            "brier":hb["selected_brier"]-hb["frozen_brier"],
            "log_loss":hb["selected_log_loss"]-hb["frozen_log_loss"],
        },
        "holdout_beats_frozen_both_metrics":improved,
        "adjudication":"RESEARCH_SIGNAL_FOR_FULL_DC_CHALLENGER" if improved else "NO_PROMOTION_TIME_DECAY_NOT_SUPERIOR_ON_HOLDOUT",
        "scope_note":"Tests exponential recency weighting inside MATRIX current lambda construction; this is not a full Dixon-Coles attack/defence MLE and does not estimate rho.",
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
    print(json.dumps({"status":"PASS","row_count":out["row_count"],"selected_half_life_days":out["selected_half_life_days"],"holdout_beats_frozen_both_metrics":out["holdout_beats_frozen_both_metrics"],"artifact_sha256":out["artifact_sha256"]},sort_keys=True))

if __name__=="__main__": main()
