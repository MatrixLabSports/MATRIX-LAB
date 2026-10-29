from tools.telegram_paid_source_static_audit import audit


def test_paid_dependencies_are_detected_without_network():
    workflow = """cron: "7,22,37,52 * * * *"
python -m tools.football_subscription_deadline_guard --require-paid-use --require-key
test -n "$API_FOOTBALL_KEY"
"""
    supervisor = """API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED
API_FOOTBALL_KEY_NOT_CONFIGURED
"https://v3.football.api-sports.io/odds"
paid_football_quote_transport_allowed()
"""
    result = audit(workflow, supervisor)
    assert result["verdict"] == "PAID_SOURCE_DEPENDENCIES_REMAIN_FAIL_CLOSED"
    assert result["provider_calls"] == 0
    assert result["telegram_calls"] == 0
    assert result["independent_live_signal_supervisor_certified"] is False


def test_missing_guard_never_certifies():
    result = audit("", "")
    assert result["verdict"] == "MANUAL_REVIEW_REQUIRED"
