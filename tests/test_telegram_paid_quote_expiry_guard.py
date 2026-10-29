"""No-network proof that both paid quote transports fail closed after cutoff."""
from unittest.mock import Mock, patch

from tools import telegram_green_signal_alerts as alerts


def test_exact_offer_expired_does_not_call_http():
    session = Mock()
    with patch.object(alerts, "paid_football_quote_transport_allowed", return_value=False):
        diagnostic = {}
        result = alerts.exact_over25_offer(session, "EXPIRED_KEY", "123", 0.7, diagnostic=diagnostic)
    assert result is None
    assert diagnostic["status"] == "BLOCKED_PAID_API_SUBSCRIPTION_EXPIRED"
    session.get.assert_not_called()


def test_pinnacle_fallback_expired_does_not_call_http():
    session = Mock()
    with patch.object(alerts, "paid_football_quote_transport_allowed", return_value=False):
        diagnostic = {}
        result = alerts.api_football_pinnacle_over25_reference(session, "EXPIRED_KEY", "123", 0.7, diagnostic)
    assert result is None
    assert diagnostic["status"] == "BLOCKED_PAID_API_SUBSCRIPTION_EXPIRED"
    session.get.assert_not_called()


def test_paid_window_uses_policy_not_presence_of_key():
    with patch.object(alerts, "football_paid_window_evaluate", return_value={"paid_window_active": False, "post_cutoff_override": False}):
        assert alerts.paid_football_quote_transport_allowed() is False
