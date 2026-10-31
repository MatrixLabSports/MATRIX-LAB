from tools.live_tennis_bulk_collector import quota_guard_payload


def test_quota_guard_blocks_without_bypassing_reserve():
    guard=quota_guard_payload(
        operational_date="2026-10-10",
        usage={"tier":"free","limits":{"per_day":100}},
        remaining=20,
        reserve_calls=20,
        requested_cycles=6,
        executed_cycles=0,
        status="BLOCKED_BY_RESERVE",
    )
    assert guard["status"]=="BLOCKED_BY_RESERVE"
    assert guard["capture_performed"] is False
    assert guard["remaining_before_run"]==20
    assert guard["reserve_calls"]==20
    assert guard["protections"]["reserve_not_bypassed"] is True
    assert guard["protections"]["real_money"]=="BLOCKED"


def test_quota_guard_records_allowed_capture():
    guard=quota_guard_payload(
        operational_date="2026-10-10",
        usage={"tier":"free","limits":{"per_day":100}},
        remaining=26,
        reserve_calls=20,
        requested_cycles=6,
        executed_cycles=6,
        status="CAPTURE_ALLOWED",
    )
    assert guard["status"]=="CAPTURE_ALLOWED"
    assert guard["capture_performed"] is True
    assert guard["executed_cycles"]==6
