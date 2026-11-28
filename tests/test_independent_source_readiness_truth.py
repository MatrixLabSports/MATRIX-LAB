"""Regression checks for offline-only post-expiry readiness.

No external HTTP calls, secrets, or Telegram delivery are required.
"""
from datetime import date

from tools.football_subscription_deadline_guard import evaluate_independent_sources


def test_readiness_does_not_certify_telegram_or_authorize_signals(monkeypatch):
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", raising=False)
    status = evaluate_independent_sources(date(2026, 10, 30))
    assert status["paid_api_football_usable"] is False
    assert status["independent_source_supervision_allowed"] is True
    assert status["independent_source_network_calls_authorized_by_this_check"] is False
    assert status["operational_telegram_without_paid_api_certified"] is False
    assert status["signal_emission_authorized_by_this_check"] is False
    assert status["real_money"] == "BLOCKED"
    assert status["automatic_wagering"] is False


def test_paid_override_does_not_certify_independent_delivery(monkeypatch):
    monkeypatch.setenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", "true")
    status = evaluate_independent_sources(date(2026, 10, 30))
    assert status["paid_api_football_usable"] is True
    assert status["operational_telegram_without_paid_api_certified"] is False
    assert status["signal_emission_authorized_by_this_check"] is False
    assert status["independent_source_network_calls_authorized_by_this_check"] is False
