from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping

SETTLED=Path("evidence/api_football/model_validation/benter_second_stage/2026-10-16/MATRIX_BENTER_ALL_CANDIDATE_SETTLED_V1.json")
OUT=Path("evidence/api_football/model_validation/MATRIX_BENTER_SECOND_STAGE_DATASET_READINESS_V2.json")
MIN_TRIPLETS=300

def _sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def build(data:Mapping[str,Any])->dict[str,Any]:
    rows=[r for r in data.get("rows",[]) if isinstance(r,Mapping)]
    triplets=[r for r in rows if r.get("model_probability") is not None and r.get("market_probability_devigged_consensus") is not None and r.get("outcome_over25") is not None]
    n=len(triplets)
    ready=n>=MIN_TRIPLETS
    out={
      "schema":"MATRIX_BENTER_SECOND_STAGE_DATASET_READINESS_V2",
      "source_schema":data.get("schema"),
      "all_candidate_row_count":len(rows),
      "valid_model_market_outcome_triplets":n,
      "minimum_triplets_required":MIN_TRIPLETS,
      "remaining_to_readiness":max(0,MIN_TRIPLETS-n),
      "fusion_training_ready":ready,
      "adjudication":"READY_FOR_RESEARCH_ONLY_CHRONOLOGICAL_SECOND_STAGE_FIT" if ready else "BLOCKED_ACCUMULATING_ALL_CANDIDATE_TRIPLETS",
      "dataset_requirements":{
        "all_scored_candidates_required":True,
        "devigged_market_consensus_required":True,
        "final_outcome_required":True,
        "chronological_split_required_before_fit":True,
        "production_fit_forbidden":True,
      },
      "governance":{
        "research_only":True,
        "production_p_matrix_modified":False,
        "market_probability_fused_into_production":False,
        "second_stage_fusion_enabled":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED"
      }
    }
    out["artifact_sha256"]=_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    data=json.loads(SETTLED.read_text())
    out=build(data)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print(json.dumps({"status":"PASS","triplets":out["valid_model_market_outcome_triplets"],"remaining":out["remaining_to_readiness"],"ready":out["fusion_training_ready"],"artifact_sha256":out["artifact_sha256"]},sort_keys=True))

if __name__=="__main__": main()
