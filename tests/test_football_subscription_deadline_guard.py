from datetime import date

import pytest

from tools.football_subscription_deadline_guard import evaluate, evaluate_independent_sources


def test_api_football_paid_window_active_through_october_28(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY","test-key")
    x=evaluate(date(2026,10,28),require_paid_use=True,require_key=True)
    assert x["paid_window_active"] is True
    assert x["days_remaining_inclusive"] == 1
    assert x["renewal_authorized"] is False


def test_api_football_paid_use_fails_closed_after_october_28(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY","test-key")
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED",raising=False)
    with pytest.raises(SystemExit,match="API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED"):
        evaluate(date(2026,10,29),require_paid_use=True,require_key=True)


def test_odds_api_net_is_not_blocked_by_api_football_expiry(monkeypatch):
    x=evaluate(date(2026,10,29))
    assert x["odds_api_net_covered_by_this_expiry_rule"] is False


def test_independent_sources_remain_governed_after_paid_expiry(monkeypatch):
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", raising=False)
    x = evaluate_independent_sources(date(2026, 10, 29))
    assert x["paid_api_football_usable"] is False
    assert x["independent_source_supervision_allowed"] is True
    assert x["independent_source_network_calls_authorized_by_this_check"] is False
    assert x["api_football_free_tier_current_season_coverage_verified"] is False
    assert x["real_money"] == "BLOCKED"
    assert x["automatic_wagering"] is False


def test_independent_source_readiness_does_not_override_paid_gate(monkeypatch):
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", raising=False)
    evaluate_independent_sources(date(2026, 10, 29))
    with pytest.raises(SystemExit, match="API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED"):
        evaluate(date(2026, 10, 29), require_paid_use=True)
