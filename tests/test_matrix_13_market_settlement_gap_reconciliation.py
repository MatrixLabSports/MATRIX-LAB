"""Synthetic-only integrity and no-promotion regression for 13 exact FT cohorts."""
from copy import deepcopy
import pytest
from tools.matrix_13_market_settlement_gap_reconciliation import reconcile

CORE=["MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2",
      "DOUBLE_CHANCE_12","TOTAL_GOALS_OVER_UNDER"]

def snapshots():
    names=CORE+[f"PERIOD_MARKET_{i}" for i in range(8)]
    all_lanes={k:{"display_name":k,"prospective_unique_count":727 if k in CORE else 634}
               for k in names}
    for i in range(29):
        all_lanes[f"OTHER_{i}"]={"display_name":f"OTHER_{i}","prospective_unique_count":0}
    reg={"lanes":all_lanes,"generated_at_utc":"2026-11-18T10:13:42+00:00"}
    exact_lanes=[]; score_lanes=[]
    for k in names:
        final=604 if k in CORE else 501
        exact_lanes.append({"market_key":k,"prospective_valid_freezes":all_lanes[k]["prospective_unique_count"],
                            "exact_cohort_final_verified":final,"telegram_authorized_by_audit":False})
        score_lanes.append({
            "market_key":k,"exact_verified_ft_count":final,"eligible_to_test":final>=600,
            "promoted":False,"verdict":"PASS_SCORING_COMPARISON_NO_PROMOTION" if k in CORE else "HOLD_BELOW_600_PROSPECTIVE_EXACT_FT",
            **({"reference_evaluable_count":final,
                "proper_scoring":{"delta_brier_challenger_minus_poisson":-.01,
                                  "delta_log_loss_challenger_minus_poisson":-.02}}
               if k in CORE else {}),
        })
    exact={"status":"RESEARCH_AUDIT_NO_PROMOTION","lanes":exact_lanes,
           "summary":{"markets_targeted":13,"markets_with_600_exact_final":5}}
    score={"status":"PASS_READ_ONLY_NO_PROMOTION","lanes":score_lanes,
           "summary":{"gate600_final_count":5,"formal_core_scoring_comparisons_completed":5},
           "generated_at_utc":"2026-11-18T03:09:34+00:00"}
    return reg, exact, score

def test_distinguishes_13_freeze_gates_from_five_settled_gates():
    d=reconcile(*snapshots())
    assert d["summary"]["market_lanes_total"]==42
    assert d["summary"]["advanced_market_lanes"]==13
    assert d["summary"]["exact_final_600_achieved"]==5
    assert d["summary"]["exact_final_below_600"]==8
    assert d["summary"]["automatically_promoted"]==0
    assert d["telegram_authorized"] is False

def test_600_final_requires_exact_matching_counts():
    reg, exact, score = snapshots()
    exact["lanes"][0]["exact_cohort_final_verified"]=600
    with pytest.raises(ValueError,match="RECONCILIATION_PROSPECTIVE_VS_SETTLED_CONFLICT"):
        reconcile(reg,exact,score)

def test_missing_proper_scores_for_600_final_fails():
    reg, exact, score = snapshots()
    score["lanes"][0].pop("proper_scoring")
    with pytest.raises(ValueError,match="RECONCILIATION_MISSING_FORMAL_METRICS"):
        reconcile(reg,exact,score)

def test_markets_below_600_cannot_get_scored():
    reg, exact, score = snapshots()
    score["lanes"][-1]["proper_scoring"]={"delta_brier_challenger_minus_poisson":-.1}
    with pytest.raises(ValueError,match="RECONCILIATION_PREMATURE_SCORING"):
        reconcile(reg,exact,score)

def test_refuse_model_promotion():
    reg, exact, score=snapshots()
    score["lanes"][0]["promoted"]=True
    with pytest.raises(ValueError,match="RECONCILIATION_PROSPECTIVE_VS_SETTLED_CONFLICT"):
        reconcile(reg,exact,score)

def test_market_lane_identity_conflict_fails():
    reg,exact,score=snapshots()
    score["lanes"][0]["market_key"]="OTHER_0"
    with pytest.raises(ValueError,match="RECONCILIATION_MARKET_KEYS_NOT_IDENTICAL"):
        reconcile(reg,exact,score)

def test_proper_scoring_worse_than_reference_never_passes():
    reg,exact,score=snapshots()
    score["lanes"][0]["proper_scoring"]["delta_brier_challenger_minus_poisson"]=.02
    result=reconcile(reg,exact,score)
    first=next(x for x in result["entries"] if x["lane"]==CORE[0])
    assert first["proper_scoring_status"]=="NO_GO_PROPER_SCORING"
    assert first["production_authorized"] is False
