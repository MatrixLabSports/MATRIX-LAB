from datetime import datetime, timezone

from tools.paid_api_utilization_watchdog import evaluate


def test_watchdog_closes_cleanly_after_deadline():
    x=evaluate(datetime(2026,10,29,12,0,tzinfo=timezone.utc))
    assert x["paid_window_active"] is False
    assert x["status"]=="PASS_WINDOW_CLOSED_NO_RENEWAL"
    assert x["real_money"]=="BLOCKED"
