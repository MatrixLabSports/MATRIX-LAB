from tools.api_football_prospective_horizon import _day_window


def test_football_world_calendar_day_is_exact_bogota_day():
    w = _day_window("2026-10-01")
    assert w["calendar_day_start_local"] == "2026-10-01T00:00:00-05:00"
    assert w["calendar_day_end_local"] == "2026-10-01T23:59:59-05:00"
    assert w["calendar_day_start_utc"] == "2026-10-01T05:00:00+00:00"
    assert w["calendar_day_end_utc"] == "2026-10-02T04:59:59+00:00"
