from tools.cor0203_rapidapi_durable_discovery import build_hourly_discovery_queue


def test_tennis_discovery_preserves_full_bogota_day_after_utc_rollover():
    q = build_hourly_discovery_queue(
        as_of_utc="2026-10-02T02:30:00+00:00",
        days=4,
    )
    item = q["queue"][0]
    # 02:30 UTC is still 21:30 on Oct 1 in Bogota. The governed world
    # calendar must therefore continue covering Oct 1 through 23:59:59 local.
    assert ":2026-10-01:2026-10-04" in item["subject_key"]


def test_tennis_discovery_rolls_day_only_at_bogota_midnight():
    before = build_hourly_discovery_queue(
        as_of_utc="2026-10-02T04:59:59+00:00",
        days=4,
    )
    after = build_hourly_discovery_queue(
        as_of_utc="2026-10-02T05:00:00+00:00",
        days=4,
    )
    assert ":2026-10-01:2026-10-04" in before["queue"][0]["subject_key"]
    assert ":2026-10-02:2026-10-05" in after["queue"][0]["subject_key"]
