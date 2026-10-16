from tools.matrix_edge_attribution_over25 import build

def test_edge_attribution_is_price_edge_only_and_does_not_invent_features():
    source={
        "bet_shadow":[{
            "fixture_id":"1",
            "match":"A vs B",
            "kickoff_utc":"2026-10-16T18:00:00+00:00",
            "p_over_2_5":0.62,
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
    assert artifact["row_count"] == 1
    row=artifact["rows"][0]
    assert round(row["break_even_probability"],6) == round(1/1.8,6)
    assert round(row["edge_probability_points"],6) == round((0.62-(1/1.8))*100,6)
    assert round(row["expected_value"],6) == round(0.62*1.8-1,6)
    assert row["edge_attribution"]["feature_level_drivers"] is None
    assert row["edge_attribution"]["feature_level_driver_status"] == "NOT_AVAILABLE_IN_CURRENT_ENGINE_TRACE"
    assert row["protections"]["feature_contributions_invented"] is False
    assert row["protections"]["p_matrix_modified"] is False
    assert artifact["governance"]["real_money"] == "BLOCKED"

def test_edge_attribution_uses_best_policy_offer_only():
    source={
        "bet_shadow":[{
            "fixture_id":"2",
            "match":"C vs D",
            "kickoff_utc":"2026-10-16T20:00:00+00:00",
            "p_over_2_5":0.65,
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
