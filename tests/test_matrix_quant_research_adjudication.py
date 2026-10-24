from tools.matrix_quant_research_adjudication import build

def test_quant_reference_adjudication_keeps_frozen_engine_when_challengers_lose():
    payloads={
        "dc_relevance":{"row_count":2379,"finding":"LOW_SCORE_TAU_WITH_FIXED_LAMBDAS_DOES_NOT_CHANGE_OVER25","max_abs_over25_delta":1e-16},
        "dc_full_over25":{"holdout_beats_frozen_both_metrics":False,"holdout_row_count":946,"holdout_delta_dc_minus_frozen":{"brier":0.016,"log_loss":0.048},"adjudication":"NO_PROMOTION_DIXON_COLES_NOT_SUPERIOR_ON_HOLDOUT"},
        "dc_full":{"holdout_beats_frozen_both_metrics":False,"holdout_comparable_n":490,"aggregate_holdout":{"delta_dc_minus_frozen":{"brier":0.014,"log_loss":0.033}},"adjudication":"NO_PROMOTION_DIXON_COLES_NOT_SUPERIOR_ON_HOLDOUT"},
        "time_decay":{"holdout_beats_frozen_both_metrics":False,"row_count":2379,"selected_half_life_days":180,"metrics":{"holdout":{"n":714}},"holdout_delta_selected_minus_frozen":{"brier":0.0001,"log_loss":0.0003},"adjudication":"NO_PROMOTION_TIME_DECAY_NOT_SUPERIOR_ON_HOLDOUT"},
    }
    out=build(payloads,{k:"x"*64 for k in payloads})
    assert out["adjudication"]=="KEEP_FROZEN_PRODUCTION_ENGINE_NO_DIXON_COLES_OR_TIME_DECAY_PROMOTION"
    assert out["benter_second_stage_market_fusion"]["production_enabled"] is False
    assert out["governance"]["p_matrix_modified"] is False
    assert out["governance"]["odds_used_to_generate_initial_probability"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
