from tools.matrix_benter_second_stage_readiness_audit import build

def test_benter_readiness_blocks_selected_small_sample():
    events=[
      {"event_type":"DECISION_FROZEN","payload":{"fixture_id":"1","model_probability":0.62,"decimal_odds":1.8}}
    ]
    telegram={"settlements":[{"fixture_id":"1","won":True,"status":"FINAL"}]}
    out=build(events,telegram)
    assert out["decision_count"]==1
    assert out["matched_model_market_outcome_triplets"]==1
    assert out["readiness"]["benter_style_second_stage_fit_allowed"] is False
    assert "CURRENT_MARKET_SAMPLE_IS_SIGNAL_SELECTED_NOT_BROAD_UNBIASED_MARKET_SAMPLE" in out["readiness"]["reason_codes"]
    assert out["governance"]["production_p_matrix_modified"] is False
    assert out["governance"]["market_probability_fused_into_production"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
