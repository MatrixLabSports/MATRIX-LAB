from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from math import log
from pathlib import Path
from typing import Any, Mapping

MILESTONE=Path("evidence/market_portfolio/MATRIX_FOOTBALL_5000_SETTLED_MILESTONE_LAST.json")
LEDGER=Path("evidence/api_football/prospective_calibration/ledger.jsonl")
FREEZE=Path("evidence/api_football/prospective_market_freeze/freeze.json")
OUT=Path("evidence/api_football/calibration_v2/MATRIX_FOOTBALL_FIXED_PREFIX_5000_AUDIT_LAST.json")
TARGET=5000
EPS=1e-15


def _json(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v


def _jsonl(path:Path)->list[dict[str,Any]]:
    out=[]
    for n,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not raw.strip(): continue
        v=json.loads(raw)
        if not isinstance(v,dict): raise ValueError(f"EXPECTED_OBJECT_JSONL:{path}:{n}")
        out.append(v)
    return out


def _sha(v:Any)->str:
    raw=json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _ece(probs:list[float], ys:list[int])->dict[str,Any]:
    n=len(probs)
    bins=[]; total=0.0
    for i in range(10):
        lo=i/10; hi=(i+1)/10
        idx=[k for k,p in enumerate(probs) if (lo<=p<hi) or (i==9 and p==1.0)]
        if not idx: continue
        mp=sum(probs[k] for k in idx)/len(idx)
        oy=sum(ys[k] for k in idx)/len(idx)
        gap=abs(mp-oy)
        total+=(len(idx)/n)*gap
        bins.append({"lower":lo,"upper":hi,"count":len(idx),"mean_probability":mp,"observed_rate":oy,"absolute_gap":gap})
    return {"method":"EQUAL_WIDTH_10_BINS","ece":total,"nonempty_bins":bins}


def _binary(rows:list[dict[str,Any]], cfun, pfun, yfun)->dict[str,Any]:
    cp=[_clip(cfun(r)) for r in rows]; pp=[_clip(pfun(r)) for r in rows]; ys=[int(yfun(r)) for r in rows]
    def one(ps):
        return {
            "sample_size":len(rows),
            "brier_score":sum((p-y)**2 for p,y in zip(ps,ys))/len(rows),
            "log_loss":sum(-(y*log(p)+(1-y)*log(1-p)) for p,y in zip(ps,ys))/len(rows),
            "ece":_ece(ps,ys),
        }
    c=one(cp); p=one(pp)
    db=c["brier_score"]-p["brier_score"]; dl=c["log_loss"]-p["log_loss"]
    return {"challenger":c,"poisson":p,"delta_brier_challenger_minus_poisson":db,"delta_log_loss_challenger_minus_poisson":dl,"beats_poisson_brier":db<0,"beats_poisson_log_loss":dl<0,"directional_pass":db<0 and dl<0}


def _one_x_two(rows:list[dict[str,Any]])->dict[str,Any]:
    cb=0.0; pb=0.0; cl=0.0; pl=0.0; cc=[]; pc=[]; cy=[]; py=[]
    for r in rows:
        y=r["outcomes"]["1x2"]; c=r["frozen_challenger_probabilities"]["1x2"]; p=r["frozen_poisson_reference"]["1x2"]
        for k in ("H","D","A"):
            yy=1.0 if y==k else 0.0
            cb+=(float(c[k])-yy)**2; pb+=(float(p[k])-yy)**2
        cl+=-log(_clip(float(c[y]))); pl+=-log(_clip(float(p[y])))
        ck=max(("H","D","A"),key=lambda k:float(c[k])); pk=max(("H","D","A"),key=lambda k:float(p[k]))
        cc.append(float(c[ck])); pc.append(float(p[pk])); cy.append(int(ck==y)); py.append(int(pk==y))
    n=len(rows)
    cm={"sample_size":n,"brier_score":cb/n,"log_loss":cl/n,"top_label_ece":_ece(cc,cy),"accuracy":sum(cy)/n}
    pm={"sample_size":n,"brier_score":pb/n,"log_loss":pl/n,"top_label_ece":_ece(pc,py),"accuracy":sum(py)/n}
    db=cm["brier_score"]-pm["brier_score"]; dl=cm["log_loss"]-pm["log_loss"]
    return {"challenger":cm,"poisson":pm,"delta_brier_challenger_minus_poisson":db,"delta_log_loss_challenger_minus_poisson":dl,"beats_poisson_brier":db<0,"beats_poisson_log_loss":dl<0,"directional_pass":db<0 and dl<0}


def _metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    one=_one_x_two(rows)
    over=_binary(rows,
        lambda r:float(r["frozen_challenger_probabilities"]["over_2_5"]),
        lambda r:float(r["frozen_poisson_reference"]["over_2_5"]),
        lambda r:bool(r["outcomes"]["over_2_5"]))
    under=_binary(rows,
        lambda r:1.0-float(r["frozen_challenger_probabilities"]["over_2_5"]),
        lambda r:1.0-float(r["frozen_poisson_reference"]["over_2_5"]),
        lambda r:not bool(r["outcomes"]["over_2_5"]))
    btts=_binary(rows,
        lambda r:float(r["frozen_challenger_probabilities"]["btts_v2"]),
        lambda r:float(r["frozen_poisson_reference"]["btts"]),
        lambda r:bool(r["outcomes"]["btts"]))
    for key in ("1X","X2","12"):
        pass
    dc={
      "DOUBLE_CHANCE_1X":_binary(rows,
        lambda r:float(r["frozen_challenger_probabilities"]["1x2"]["H"])+float(r["frozen_challenger_probabilities"]["1x2"]["D"]),
        lambda r:float(r["frozen_poisson_reference"]["1x2"]["H"])+float(r["frozen_poisson_reference"]["1x2"]["D"]),
        lambda r:r["outcomes"]["1x2"] in {"H","D"}),
      "DOUBLE_CHANCE_X2":_binary(rows,
        lambda r:float(r["frozen_challenger_probabilities"]["1x2"]["D"])+float(r["frozen_challenger_probabilities"]["1x2"]["A"]),
        lambda r:float(r["frozen_poisson_reference"]["1x2"]["D"])+float(r["frozen_poisson_reference"]["1x2"]["A"]),
        lambda r:r["outcomes"]["1x2"] in {"D","A"}),
      "DOUBLE_CHANCE_12":_binary(rows,
        lambda r:float(r["frozen_challenger_probabilities"]["1x2"]["H"])+float(r["frozen_challenger_probabilities"]["1x2"]["A"]),
        lambda r:float(r["frozen_poisson_reference"]["1x2"]["H"])+float(r["frozen_poisson_reference"]["1x2"]["A"]),
        lambda r:r["outcomes"]["1x2"] in {"H","A"}),
    }
    return {"MATCH_RESULT_1X2":one,"TOTAL_GOALS_OVER_2_5":over,"TOTAL_GOALS_UNDER_2_5":under,"BTTS_V2":btts,**dc}


def _temporal(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    ordered=sorted(rows,key=lambda r:(str(r["kickoff_utc"]),str(r["fixture_id"])))
    out=[]
    for i in range(5):
        a=(len(ordered)*i)//5; b=(len(ordered)*(i+1))//5
        chunk=ordered[a:b]
        if not chunk: continue
        m=_metrics(chunk)
        out.append({"segment":i+1,"sample_size":len(chunk),"start_kickoff_utc":chunk[0]["kickoff_utc"],"end_kickoff_utc":chunk[-1]["kickoff_utc"],"directional_pass_by_market":{k:v["directional_pass"] for k,v in m.items()}})
    return out


def build(generated_at:datetime|None=None)->dict[str,Any]:
    milestone=_json(MILESTONE)
    rows=_jsonl(LEDGER)
    if milestone.get("status")!="PASS": raise ValueError("MILESTONE_NOT_PASS")
    if len(rows)!=int(milestone["current_settled_count"]): raise ValueError("MILESTONE_LEDGER_COUNT_MISMATCH")
    if len({str(r["fixture_id"]) for r in rows})!=len(rows): raise ValueError("DUPLICATE_FIXTURE_ID")
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()

    base={
      "schema":"MATRIX_FOOTBALL_FIXED_PREFIX_5000_AUDIT_V1",
      "generated_at_utc":now,
      "status":"PASS",
      "target_settled_count":TARGET,
      "current_settled_count":len(rows),
      "automatic_promotion":False,
      "protections":{
        "fixed_prefix_only":True,"final_ft_only":True,"append_only_source":True,
        "parameter_tuning_allowed":False,"refit_allowed":False,
        "historical_backfill":False,"post_start_backfill":False,
        "odds_used_to_generate_probability":False,"automatic_wagering":False,"real_money":"BLOCKED"
      }
    }
    if len(rows)<TARGET:
        return base|{
          "audit_state":"SEALED_BELOW_5000",
          "remaining_to_5000":TARGET-len(rows),
          "metrics_opened":False,
          "prefix":None,
          "metrics":None,
          "temporal_stability":None,
          "competition_concentration":None,
          "audit_verdict":"HOLD",
          "next_required_action":"CONTINUE_FINAL_ONLY_SETTLEMENT_UNTIL_5000"
        }

    prefix=rows[:TARGET]
    freeze=_json(FREEZE)
    by_id={str(r.get("fixture_id")):r for r in freeze.get("rows") or [] if isinstance(r,Mapping)}
    comps={}
    for r in prefix:
        f=by_id.get(str(r["fixture_id"])) or {}
        key=str(f.get("competition_name") or f.get("competition_id") or "UNKNOWN")
        comps[key]=comps.get(key,0)+1
    metrics=_metrics(prefix)
    directional_all=all(v["directional_pass"] for v in metrics.values())
    verdict="PASS" if directional_all else "HOLD"
    return base|{
      "audit_state":"OPEN_FIXED_PREFIX_5000",
      "remaining_to_5000":0,
      "metrics_opened":True,
      "prefix":{
        "observation_count":TARGET,
        "fixture_ids_sha256":_sha([str(r["fixture_id"]) for r in prefix]),
        "record_hashes_sha256":_sha([str(r["record_sha256"]) for r in prefix]),
        "first_fixture_id":str(prefix[0]["fixture_id"]),
        "last_fixture_id":str(prefix[-1]["fixture_id"])
      },
      "metrics":metrics,
      "temporal_stability":{"method":"CHRONOLOGICAL_QUINTILES","segments":_temporal(prefix)},
      "competition_concentration":{
        "competition_count":len(comps),
        "top_competitions":sorted(({"competition":k,"count":v,"share":v/TARGET} for k,v in comps.items()),key=lambda x:(-x["count"],x["competition"]))[:20]
      },
      "audit_verdict":verdict,
      "audit_verdict_policy":"PASS_ONLY_IF_ALL_REPORTED_MARKETS_BEAT_POISSON_ON_BRIER_AND_LOGLOSS; OTHERWISE_HOLD_FOR_REVIEW; NO_AUTO_PROMOTION",
      "next_required_action":"REVIEW_FIXED_PREFIX_5000_AUDIT_NO_AUTO_PROMOTION"
    }


def main()->None:
    r=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(r,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":r["status"],"audit_state":r["audit_state"],"current_settled_count":r["current_settled_count"],
      "remaining_to_5000":r["remaining_to_5000"],"metrics_opened":r["metrics_opened"],
      "audit_verdict":r["audit_verdict"],"real_money":"BLOCKED"
    },sort_keys=True))


if __name__=="__main__":
    main()
