from tools.matrix_edge_attribution_over25 import build

def _trace():
    return {
        "trace_schema":"MATRIX_OVER25_FEATURE_TRACE_V1",
        "space":"LOGIT",
        "poisson_probability":0.66,
        "baseline_probability":0.58,
        "poisson_logit":0.6632942174,
        "baseline_logit":0.3227733923,
        "poisson_weight":0.6,
        "baseline_weight":0.4,
        "intercept":0.0,
        "poisson_weighted_logit_contribution":0.3979765304,
        "baseline_weighted_logit_contribution":0.1291093569,
        "intercept_logit_contribution":0.0,
        "pooled_logit":0.5270858873,
        "reconstructed_probability":0.6288022142,
        "probability_modified_by_trace":False,
        "odds_used_in_trace":False,
    }

def test_edge_attribution_v2_uses_real_engine_trace_without_modifying_p_matrix():
    source={
        "bet_shadow":[{
            "fixture_id":"1",
            "match":"A vs B",
            "kickoff_utc":"2026-10-16T18:00:00+00:00",
            "p_over_2_5":0.6288022142,
            "over25_feature_trace":_trace(),
            "best_policy_offer":{
                "bookmaker_name":"BetPlay",
                "house_key":"betplay",
                "decimal_odds":1.80,
                "quote_evidence_sha256":"q",
                "raw_sha256":"r",
                "odds_captured_at_utc":"2026-10-16T15:00:00+00:00",
                "provider_quote_updated_at_utc":"2026-10-16T14:59:00+00:00"
            }
        }]
    }
    artifact=build(source, generated_at="2026-10-16T15:00:00+00:00")
    assert artifact["schema"] == "MATRIX_EDGE_ATTRIBUTION_OVER25_V2"
    assert artifact["attribution_scope"] == "MODEL_COMPONENT_LOGIT_AND_PRICE_EDGE"
    row=artifact["rows"][0]
    assert row["p_matrix"] == 0.6288022142
    assert row["edge_attribution"]["feature_level_driver_status"] == "AVAILABLE_REAL_ENGINE_TRACE"
    drivers=row["edge_attribution"]["feature_level_drivers"]
    assert [d["driver"] for d in drivers] == ["POISSON_OVER25","GROUP_BASELINE_OVER25","INTERCEPT"]
    assert drivers[0]["weighted_logit_contribution"] == 0.3979765304
    assert drivers[1]["weighted_logit_contribution"] == 0.1291093569
    assert row["edge_attribution"]["reconstructed_probability"] == 0.6288022142
    assert row["protections"]["feature_contributions_invented"] is False
    assert row["protections"]["p_matrix_modified"] is False
    assert artifact["governance"]["real_money"] == "BLOCKED"

def test_edge_attribution_v2_keeps_price_edge_separate_from_model_trace():
    source={
        "bet_shadow":[{
            "fixture_id":"2",
            "match":"C vs D",
            "kickoff_utc":"2026-10-16T20:00:00+00:00",
            "p_over_2_5":0.6288022142,
            "over25_feature_trace":_trace(),
            "best_policy_offer":{
                "bookmaker_name":"Rushbet",
                "house_key":"rushbet",
                "decimal_odds":1.70,
                "quote_evidence_sha256":"q2",
                "raw_sha256":"r2",
                "odds_captured_at_utc":"2026-10-16T16:00:00+00:00",
                "provider_quote_updated_at_utc":"2026-10-16T15:59:00+00:00"
            },
            "policy_offers":[{"decimal_odds":1.60},{"decimal_odds":1.70}]
        }]
    }
    row=build(source)["rows"][0]
    assert row["execution_house_key"] == "rushbet"
    assert row["quoted_decimal_odds"] == 1.70
    assert round(row["expected_value"],8) == round(0.6288022142*1.70-1,8)
    assert row["edge_attribution"]["feature_trace_space"] == "LOGIT"

def test_edge_attribution_v2_refuses_to_invent_missing_feature_trace():
    source={
        "bet_shadow":[{
            "fixture_id":"3",
            "match":"E vs F",
            "kickoff_utc":"2026-10-16T21:00:00+00:00",
            "p_over_2_5":0.61,
            "best_policy_offer":{
                "bookmaker_name":"Betano",
                "house_key":"betano",
                "decimal_odds":1.90
            }
        }]
    }
    row=build(source)["rows"][0]
    assert row["edge_attribution"]["feature_level_drivers"] is None
    assert row["edge_attribution"]["feature_level_driver_status"] == "NOT_AVAILABLE_IN_SOURCE_TRACE"
    assert row["protections"]["feature_contributions_invented"] is False


def test_edge_attribution_v2_keeps_model_trace_even_without_price():
    source={
        "all_rows":[{
            "fixture_id":"4",
            "match":"G vs H",
            "kickoff_utc":"2026-10-16T22:00:00+00:00",
            "p_over_2_5":0.6288022142,
            "over25_feature_trace":_trace(),
            "best_policy_offer":None,
            "decision":"BLOCKED",
            "reason":"NO_EXACT_POLICY_HOUSE_OVER25_ODDS_ABOVE_1_50"
        }]
    }
    artifact=build(source)
    assert artifact["row_count"] == 1
    assert artifact["feature_trace_available_count"] == 1
    assert artifact["priced_row_count"] == 0
    row=artifact["rows"][0]
    assert row["quoted_decimal_odds"] is None
    assert row["expected_value"] is None
    assert row["edge_attribution"]["feature_level_driver_status"] == "AVAILABLE_REAL_ENGINE_TRACE"
    assert row["protections"]["p_matrix_modified"] is False
