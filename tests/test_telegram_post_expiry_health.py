from datetime import datetime
from zoneinfo import ZoneInfo

from tools.telegram_post_expiry_health import build

BOGOTA = ZoneInfo("America/Bogota")
WORKFLOW = 'cron: "7,22,37,52 * * * *"\npython -m tools.football_subscription_deadline_guard --require-paid-use --require-key'
SUPERVISOR = 'MATRIX_API_FOOTBALL_AUTHORIZED\nprimary_offer = exact_over25_offer('


def test_post_expiry_is_blocked_without_calls():
    report = build(datetime(2026, 10, 29, 12, tzinfo=BOGOTA), WORKFLOW, SUPERVISOR)
    assert report["status"] == "POST_EXPIRY_SUPERVISOR_BLOCKED_FAIL_CLOSED"
    assert report["scheduled_supervisor_blocked_by_paid_gate"]
    assert report["schedule_15m_configured"]
    assert report["paid_provider_calls"] == 0
    assert report["telegram_delivery_certified"] is False
    assert report["real_money"] == "BLOCKED"


def test_pre_expiry_not_reported_as_post_expiry_block():
    report = build(datetime(2026, 10, 28, 12, tzinfo=BOGOTA), WORKFLOW, SUPERVISOR)
    assert report["scheduled_supervisor_blocked_by_paid_gate"] is False
    assert report["status"] == "REVIEW_REQUIRED"
