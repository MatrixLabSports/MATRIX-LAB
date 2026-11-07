from tools.matrix_benter_second_stage_fusion_readiness import build

def test_benter_fusion_blocks_without_paired_devig_market_probabilities():
    events=[
      {"event_type":"DECISION_FROZEN","payload":{"fixture_id":"1","decimal_odds":1.8}},
      {"event_type":"CLOSING_ODDS_RECORDED","payload":{"fixture_id":"1","decimal_odds":1.9}},
    ]
    out=build(events,{"status":"ACCUMULATING_SEALED_UNTIL_300"})
    assert out["decision_count"]==1
    assert out["closing_odds_count"]==1
    assert out["paired_devig_market_probability_count"]==0
    assert out["fusion_training_ready"] is False
    assert out["adjudication"]=="BLOCKED_INSUFFICIENT_PAIRED_DEVIG_MARKET_PROBABILITIES"
    assert out["governance"]["second_stage_fusion_enabled"] is False
    assert out["governance"]["production_engine_modified"] is False
    assert out["governance"]["real_money"]=="BLOCKED"

def test_benter_fusion_readiness_requires_300_paired_market_probs():
    events=[]
    for i in range(300):
        events.append({"event_type":"DECISION_FROZEN","payload":{"fixture_id":str(i)}})
        events.append({"event_type":"CLOSING_ODDS_RECORDED","payload":{"fixture_id":str(i),"fair_market_probability":0.55}})
    out=build(events,{})
    assert out["paired_devig_market_probability_count"]==300
    assert out["remaining_to_readiness"]==0
    assert out["fusion_training_ready"] is True
    assert out["adjudication"]=="READY_FOR_RESEARCH_ONLY_CHRONOLOGICAL_FUSION"
