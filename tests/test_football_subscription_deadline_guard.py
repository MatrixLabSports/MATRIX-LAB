from datetime import date

import pytest

from tools.football_subscription_deadline_guard import evaluate


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
