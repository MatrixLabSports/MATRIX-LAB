from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

ROOT=Path("evidence/api_football/model_validation")
SOURCES={
    "dc_relevance":ROOT/"MATRIX_DIXON_COLES_OVER25_RELEVANCE_AUDIT_V1.json",
    "dc_full_over25":ROOT/"MATRIX_DIXON_COLES_FULL_OVER25_CHALLENGER_V1.json",
    "dc_full":ROOT/"MATRIX_DIXON_COLES_FULL_CHALLENGER_V1.json",
    "time_decay":ROOT/"MATRIX_OVER25_TIME_DECAY_CHALLENGER_V1.json",
}
OUT=ROOT/"MATRIX_QUANT_REFERENCE_ADJUDICATION_16OCT2026.json"

def _sha_bytes(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def _canonical_sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def build(payloads:dict[str,dict], source_sha:dict[str,str])->dict:
    rel=payloads["dc_relevance"]
    dco=payloads["dc_full_over25"]
    dcf=payloads["dc_full"]
    td=payloads["time_decay"]
    facts={
        "dixon_coles_fixed_lambda_over25_changes_probability": abs(float(rel["max_abs_over25_delta"])) >= 1e-12,
        "dixon_coles_full_over25_beats_frozen_both_metrics": bool(dco["holdout_beats_frozen_both_metrics"]),
        "dixon_coles_full_beats_frozen_both_metrics": bool(dcf["holdout_beats_frozen_both_metrics"]),
        "time_decay_beats_frozen_both_metrics": bool(td["holdout_beats_frozen_both_metrics"]),
    }
    out={
        "schema":"MATRIX_QUANT_REFERENCE_ADJUDICATION_V1",
        "source_artifacts":{k:{"path":SOURCES[k].as_posix(),"sha256":source_sha[k]} for k in SOURCES},
        "verified_findings":{
            "dixon_coles_relevance":{
                "rows":int(rel["row_count"]),
                "finding":rel["finding"],
                "max_abs_over25_delta":float(rel["max_abs_over25_delta"]),
            },
            "dixon_coles_full_over25":{
                "holdout_n":int(dco["holdout_row_count"]),
                "delta_brier_dc_minus_frozen":float(dco["holdout_delta_dc_minus_frozen"]["brier"]),
                "delta_log_loss_dc_minus_frozen":float(dco["holdout_delta_dc_minus_frozen"]["log_loss"]),
                "adjudication":dco["adjudication"],
            },
            "dixon_coles_full":{
                "holdout_n":int(dcf["holdout_comparable_n"]),
                "delta_brier_dc_minus_frozen":float(dcf["aggregate_holdout"]["delta_dc_minus_frozen"]["brier"]),
                "delta_log_loss_dc_minus_frozen":float(dcf["aggregate_holdout"]["delta_dc_minus_frozen"]["log_loss"]),
                "adjudication":dcf["adjudication"],
            },
            "time_decay":{
                "rows":int(td["row_count"]),
                "selected_half_life_days":int(td["selected_half_life_days"]),
                "holdout_n":int(td["metrics"]["holdout"]["n"]),
                "delta_brier_selected_minus_frozen":float(td["holdout_delta_selected_minus_frozen"]["brier"]),
                "delta_log_loss_selected_minus_frozen":float(td["holdout_delta_selected_minus_frozen"]["log_loss"]),
                "adjudication":td["adjudication"],
            },
        },
        "facts":facts,
        "adjudication":"KEEP_FROZEN_PRODUCTION_ENGINE_NO_DIXON_COLES_OR_TIME_DECAY_PROMOTION",
        "benter_second_stage_market_fusion":{
            "status":"RESEARCH_ONLY_NOT_ENABLED",
            "reason":"REQUIRES_SEPARATE_PREREGISTERED_OOS_TEST_AND_MUST_NOT_REPLACE_INDEPENDENT_P_MATRIX",
            "production_enabled":False,
        },
        "next_research_step":"PREREGISTER_BENTER_STYLE_SECOND_STAGE_FUSION_CHALLENGER_ONLY_AFTER_SUFFICIENT_PHYSICAL_MARKET_AND_OUTCOME_SAMPLE",
        "governance":{
            "production_engine_modified":False,
            "p_matrix_modified":False,
            "telegram_modified":False,
            "odds_used_to_generate_initial_probability":False,
            "automatic_wagering":False,
            "research_only":True,
            "real_money":"BLOCKED",
        },
    }
    assert facts["dixon_coles_fixed_lambda_over25_changes_probability"] is False
    assert facts["dixon_coles_full_over25_beats_frozen_both_metrics"] is False
    assert facts["dixon_coles_full_beats_frozen_both_metrics"] is False
    assert facts["time_decay_beats_frozen_both_metrics"] is False
    out["artifact_sha256"]=_canonical_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    payloads={}
    shas={}
    for k,p in SOURCES.items():
        raw=p.read_bytes()
        payloads[k]=json.loads(raw)
        shas[k]=_sha_bytes(raw)
    out=build(payloads,shas)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "status":"PASS",
        "adjudication":out["adjudication"],
        "artifact_sha256":out["artifact_sha256"],
        "real_money":out["governance"]["real_money"],
    },sort_keys=True))

if __name__=="__main__": main()
