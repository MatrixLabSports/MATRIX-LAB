from datetime import date

import pytest

from tools.tennis_subscription_deadline_guard import evaluate


def test_paid_window_active_through_october_28(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_TENNIS_KEY", "test-key")
    x = evaluate(date(2026, 10, 28), require_paid_use=True, require_key=True)
    assert x["paid_window_active"] is True
    assert x["days_remaining_inclusive"] == 1
    assert x["renewal_authorized"] is False
    assert x["api_tennis_network_calls_allowed"] is False


def test_paid_use_fails_closed_after_october_28(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_TENNIS_KEY", "test-key")
    with pytest.raises(SystemExit, match="PAID_API_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED"):
        evaluate(date(2026, 10, 29), require_paid_use=True, require_key=True)


def test_free50_never_auto_activates(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_TENNIS_KEY", "test-key")
    x = evaluate(date(2026, 10, 22))
    assert x["free50_auto_activation_allowed"] is False
