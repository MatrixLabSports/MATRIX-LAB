from __future__ import annotations

import json
from pathlib import Path

from tools.api_football_over25_forward_validation_100 import _audit_source

ROOT=Path("evidence/api_football")
LEDGER=ROOT/"prospective_calibration"/"ledger.jsonl"
OUT=ROOT/"calibration_v2"/"MATRIX_OVER25_THRESHOLD_HITRATE_ANALYSIS_CURRENT.json"

def load_jsonl(path):
    rows=[]
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))
    return rows

def main():
    rows=load_jsonl(LEDGER)
    _audit_source(rows)
    cuts=[0.60,0.65,0.70,0.75]
    results=[]
    for cut in cuts:
        cohort=[]
        for r in rows:
            p=(r.get("frozen_challenger_probabilities") or {}).get("over_2_5")
            y=(r.get("outcomes") or {}).get("over_2_5")
            if isinstance(p,(int,float)) and isinstance(y,bool) and float(p)>=cut:
                cohort.append((float(p),bool(y)))
        n=len(cohort)
        wins=sum(1 for _,y in cohort if y)
        hit=wins/n if n else None
        mean_p=sum(p for p,_ in cohort)/n if n else None
        results.append({
            "threshold":cut,
            "sample_size":n,
            "wins":wins,
            "losses":n-wins,
            "hit_rate":hit,
            "mean_predicted_probability":mean_p,
            "observed_minus_predicted":(hit-mean_p) if n else None,
        })
    payload={
        "schema":"MATRIX_OVER25_THRESHOLD_HITRATE_ANALYSIS_V1",
        "market":"OVER_2_5",
        "source_sample_size":len(rows),
        "threshold_results":results,
        "governance":{
            "parameter_tuning_allowed":False,
            "model_files_modified":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    }
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(payload,sort_keys=True))

if __name__=="__main__":
    main()
