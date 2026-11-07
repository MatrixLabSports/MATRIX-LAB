from tools.matrix_benter_second_stage_dataset_readiness import build

def test_readiness_stays_blocked_below_300():
    rows=[]
    for i in range(41):
        rows.append({"model_probability":0.6,"market_probability_devigged_consensus":0.58,"outcome_over25":bool(i%2)})
    out=build({"schema":"MATRIX_BENTER_ALL_CANDIDATE_SETTLED_V1","rows":rows})
    assert out["valid_model_market_outcome_triplets"]==41
    assert out["remaining_to_readiness"]==259
    assert out["fusion_training_ready"] is False
    assert out["governance"]["market_probability_fused_into_production"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
