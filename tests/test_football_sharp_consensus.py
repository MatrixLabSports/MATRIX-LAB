from app.research.football.sharp_consensus import assess_sharp_consensus


def test_consensus_uses_pinnacle_circa_betfair_but_not_fanduel():
    result = assess_sharp_consensus(
        p_matrix=0.58,
        quotes=[
            {"source":"Pinnacle","over_odds":1.80,"under_odds":2.05,"quote_age_seconds":30},
            {"source":"Circa","over_odds":1.82,"under_odds":2.02,"quote_age_seconds":40},
            {"source":"Betfair","over_odds":1.81,"under_odds":2.04,"quote_age_seconds":20},
            {"source":"FanDuel","over_odds":1.95,"under_odds":1.90,"quote_age_seconds":25},
        ],
    )
    assert result["sharp_source_count"] == 3
    assert [x["source"] for x in result["sharp_rows"]] == ["pinnacle","circa","betfair"]
    assert [x["source"] for x in result["market_context_rows"]] == ["fanduel"]
    assert result["sharp_reference_policy"]["p_matrix_mutated_by_odds"] is False
    assert result["p_matrix"] == 0.58


def test_strong_disagreement_is_review_not_probability_mutation():
    result = assess_sharp_consensus(
        p_matrix=0.64,
        quotes=[
            {"source":"Pinnacle","over_odds":2.10,"under_odds":1.75,"quote_age_seconds":20},
            {"source":"Circa","over_odds":2.08,"under_odds":1.76,"quote_age_seconds":25},
        ],
    )
    assert result["status"] == "CONTRADICTION_REVIEW"
    assert result["signal_action"] == "REVIEW_ONLY"
    assert result["p_matrix"] == 0.64
    assert result["automatic_wagering"] is False
    assert result["real_money"] == "BLOCKED"


def test_stale_quote_is_rejected_fail_closed():
    result = assess_sharp_consensus(
        p_matrix=0.60,
        quotes=[
            {"source":"Pinnacle","over_odds":1.85,"under_odds":2.00,"quote_age_seconds":121},
            {"source":"Circa","over_odds":1.86,"under_odds":1.99,"quote_age_seconds":10},
        ],
    )
    assert result["status"] == "SINGLE_SHARP_REFERENCE_ONLY"
    assert result["sharp_source_count"] == 1
    assert result["rejected_rows"][0]["reason"] == "STALE_QUOTE"


def test_no_sharp_data_does_not_fake_consensus():
    result = assess_sharp_consensus(
        p_matrix=0.60,
        quotes=[
            {"source":"FanDuel","over_odds":1.90,"under_odds":1.95,"quote_age_seconds":10},
        ],
    )
    assert result["status"] == "INSUFFICIENT_SHARP_COVERAGE"
    assert result["sharp_consensus_probability"] is None
    assert result["sharp_source_count"] == 0
