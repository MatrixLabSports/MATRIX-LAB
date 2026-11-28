from tools.matrix_edge_performance_ledger import build

def test_edge_performance_ledger_stays_sealed_without_sample():
    attr={"rows":[
        {"fixture_id":"1","match":"A vs B","p_matrix":0.62,"edge_attribution":{"feature_level_driver_status":"AVAILABLE_REAL_ENGINE_TRACE","feature_level_drivers":[
            {"driver":"POISSON_OVER25","weighted_logit_contribution":0.4},
            {"driver":"GROUP_BASELINE_OVER25","weighted_logit_contribution":0.1},
        ]}},
        {"fixture_id":"2","match":"C vs D","p_matrix":0.58,"edge_attribution":{"feature_level_driver_status":"AVAILABLE_REAL_ENGINE_TRACE","feature_level_drivers":[
            {"driver":"POISSON_OVER25","weighted_logit_contribution":0.1},
            {"driver":"GROUP_BASELINE_OVER25","weighted_logit_contribution":-0.3},
        ]}},
    ]}
    telegram={"settlements":[
        {"fixture_id":"1","status":"FINAL","won":True,"paper_profit_cop":20000,"shadow_profit_units":0.8}
    ]}
    clv=[
        {"event_type":"DECISION_FROZEN","payload":{"fixture_id":"1","decimal_odds":1.8}},
        {"event_type":"CLOSING_ODDS_RECORDED","payload":{"fixture_id":"1","decimal_odds":1.9}},
    ]
    out=build(attr,telegram,clv)
    assert out["row_count"]==2
    assert out["settled_join_count"]==1
    assert out["clv_join_count"]==1
    assert out["driver_groups"]["POISSON_OVER25"]["performance_gate_open"] is False
    assert out["driver_groups"]["POISSON_OVER25"]["clv_gate_open"] is False
    assert out["governance"]["driver_superiority_claim_allowed"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
    assert out["gates"]["remaining_settled_to_open_by_driver"]["POISSON_OVER25"] == 29
    assert out["gates"]["remaining_clv_to_open_by_driver"]["POISSON_OVER25"] == 299

def test_dominant_driver_uses_absolute_real_logit_contribution():
    attr={"rows":[
        {"fixture_id":"9","match":"E vs F","p_matrix":0.49,"edge_attribution":{"feature_level_driver_status":"AVAILABLE_REAL_ENGINE_TRACE","feature_level_drivers":[
            {"driver":"POISSON_OVER25","weighted_logit_contribution":0.12},
            {"driver":"GROUP_BASELINE_OVER25","weighted_logit_contribution":-0.31},
            {"driver":"INTERCEPT","weighted_logit_contribution":0.0},
        ]}},
    ]}
    out=build(attr,{"settlements":[]},[])
    assert out["rows"][0]["dominant_model_driver"]=="GROUP_BASELINE_OVER25"
