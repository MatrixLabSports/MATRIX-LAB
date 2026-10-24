from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping

CLV=Path("evidence/clv/football/over_2_5/prospective_clv_ledger.jsonl")
STATE=Path("evidence/clv/football/over_2_5/state.json")
OUT=Path("evidence/api_football/model_validation/MATRIX_BENTER_SECOND_STAGE_FUSION_READINESS_V1.json")
MIN_PAIRED_MARKET_OBS=300

def _sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def build(events:list[Mapping[str,Any]],state:Mapping[str,Any])->dict[str,Any]:
    decisions=[e for e in events if e.get("event_type")=="DECISION_FROZEN"]
    closings=[e for e in events if e.get("event_type")=="CLOSING_ODDS_RECORDED"]
    # Current canonical CLV ledger stores the Over closing price only.
    paired_no_vig=[e for e in closings if isinstance((e.get("payload") or {}).get("fair_market_probability"),(int,float))]
    ready=len(paired_no_vig)>=MIN_PAIRED_MARKET_OBS
    out={
      "schema":"MATRIX_BENTER_SECOND_STAGE_FUSION_READINESS_V1",
      "literature_basis":"Benter 1994 combines a fundamental logit model with public implied probability estimates as a separate second-stage opinion.",
      "fundamental_probability_independence_required":True,
      "production_p_matrix_unchanged":True,
      "decision_count":len(decisions),
      "closing_odds_count":len(closings),
      "paired_devig_market_probability_count":len(paired_no_vig),
      "minimum_paired_market_observations":MIN_PAIRED_MARKET_OBS,
      "remaining_to_readiness":max(0,MIN_PAIRED_MARKET_OBS-len(paired_no_vig)),
      "fusion_training_ready":ready,
      "adjudication":"READY_FOR_RESEARCH_ONLY_CHRONOLOGICAL_FUSION" if ready else "BLOCKED_INSUFFICIENT_PAIRED_DEVIG_MARKET_PROBABILITIES",
      "blocking_reasons":[] if ready else [
        "CURRENT_CLV_LEDGER_DOES_NOT_PERSIST_PAIRED_NO_VIG_MARKET_PROBABILITY",
        "SAMPLE_BELOW_300"
      ],
      "state_status":state.get("status"),
      "governance":{
        "research_only":True,
        "odds_used_to_generate_production_probability":False,
        "second_stage_fusion_enabled":False,
        "production_engine_modified":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED"
      }
    }
    out["artifact_sha256"]=_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    events=[json.loads(x) for x in CLV.read_text().splitlines() if x.strip()]
    state=json.loads(STATE.read_text())
    out=build(events,state)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"PASS","decision_count":out["decision_count"],"closing_odds_count":out["closing_odds_count"],"paired_devig_market_probability_count":out["paired_devig_market_probability_count"],"adjudication":out["adjudication"],"artifact_sha256":out["artifact_sha256"]},sort_keys=True))

if __name__=="__main__":main()
