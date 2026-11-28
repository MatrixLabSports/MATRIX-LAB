from tools.odds_api_quota_guard import evaluate_usage, should_call_odds_api


def usage(pct: float, *, exceeded: bool = False):
    limit = 2_000_000
    return {
        "api_credits_used": limit * pct / 100,
        "api_credits_limit": limit,
        "exceeded": exceeded,
        "plan": "builder",
    }


def test_quota_stages_and_time_reservation():
    d = evaluate_usage(usage(49.9))
    assert d["stage"] == "NORMAL_T120"
    assert should_call_odds_api(d, 119 * 60)

    d = evaluate_usage(usage(50))
    assert d["stage"] == "WATCH_T120"

    d = evaluate_usage(usage(75))
    assert d["stage"] == "CONSERVE_T90_ONLY"
    assert should_call_odds_api(d, 89 * 60)
    assert not should_call_odds_api(d, 91 * 60)

    d = evaluate_usage(usage(90))
    assert d["stage"] == "RESERVE_T60_ONLY"
    assert should_call_odds_api(d, 59 * 60)
    assert not should_call_odds_api(d, 61 * 60)

    d = evaluate_usage(usage(95))
    assert d["stage"] == "RESERVE_T30_ONLY"
    assert should_call_odds_api(d, 29 * 60)
    assert not should_call_odds_api(d, 31 * 60)


def test_exhausted_monthly_quota_blocks_all_odds_api_calls():
    d = evaluate_usage(usage(100))
    assert d["stage"] == "BLOCKED_EXHAUSTED"
    assert d["api_calls_allowed"] is False
    assert not should_call_odds_api(d, 60)


def test_provider_exceeded_flag_blocks_even_if_counter_is_below_limit():
    d = evaluate_usage(usage(80, exceeded=True))
    assert d["stage"] == "BLOCKED_EXHAUSTED"
    assert not should_call_odds_api(d, 60)
