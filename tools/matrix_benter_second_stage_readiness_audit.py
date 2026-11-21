from __future__ import annotations
import hashlib,json
from pathlib import Path

CLV=Path("evidence/clv/football/over_2_5/prospective_clv_ledger.jsonl")
TELE=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
OUT=Path("evidence/api_football/model_validation/MATRIX_BENTER_SECOND_STAGE_READINESS_AUDIT_V1.json")

def build(events,telegram):
    decisions={}
    for e in events:
        if e.get("event_type")=="DECISION_FROZEN":
            p=e.get("payload") or {}
            decisions[str(p.get("fixture_id"))]=p
    settlements={str(x.get("fixture_id")):x for x in telegram.get("settlements",[]) if isinstance(x,dict)}
    matched=[]
    for fid,d in decisions.items():
        s=settlements.get(fid)
        if not s: continue
        matched.append({
          "fixture_id":fid,
          "model_probability":d.get("model_probability"),
          "market_probability_raw_entry":1.0/float(d["decimal_odds"]),
          "outcome_over25":bool(s.get("won")),
          "entry_odds":d.get("decimal_odds"),
          "settlement_status":s.get("status"),
        })
    out={
      "schema":"MATRIX_BENTER_SECOND_STAGE_READINESS_AUDIT_V1",
      "decision_count":len(decisions),
      "matched_model_market_outcome_triplets":len(matched),
      "matched_rows":matched,
      "readiness":{
        "benter_style_second_stage_fit_allowed":False,
        "reason_codes":[
          "CURRENT_MARKET_SAMPLE_IS_SIGNAL_SELECTED_NOT_BROAD_UNBIASED_MARKET_SAMPLE",
          "CURRENT_TRIPLET_SAMPLE_SMALL_FOR_STABLE_SECOND_STAGE_ESTIMATION",
          "PUBLIC_PROBABILITY_IS_RAW_ENTRY_IMPLIED_NOT_DEVIGGED_CONSENSUS",
          "PRODUCTION_NO_ODDS_TO_P_RULE_REMAINS_IN_FORCE"
        ],
        "required_next_data":"PROSPECTIVE_ALL_CANDIDATE_MODEL_P_PLUS_DEVIGGED_MARKET_P_PLUS_FINAL_OUTCOME",
      },
      "governance":{
        "research_only":True,"production_p_matrix_modified":False,
        "market_probability_fused_into_production":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
      }
    }
    out["artifact_sha256"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return out

def main():
    events=[json.loads(x) for x in CLV.read_text().splitlines() if x.strip()]
    tele=json.loads(TELE.read_text())
    out=build(events,tele)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"PASS","decision_count":out["decision_count"],"matched_triplets":out["matched_model_market_outcome_triplets"],"fit_allowed":out["readiness"]["benter_style_second_stage_fit_allowed"],"artifact_sha256":out["artifact_sha256"]},sort_keys=True))

if __name__=="__main__":main()
