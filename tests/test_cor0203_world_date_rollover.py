from datetime import datetime, timezone

import pytest

from tools.cor0203_world_date_rollover import (
    ROLLOVER_HOUR_BOGOTA,
    resolve_world_date,
)


def test_rollover_hour_is_15_bogota():
    assert ROLLOVER_HOUR_BOGOTA == 15


def test_before_15_bogota_uses_same_day():
    now = datetime(2026, 10, 15, 19, 59, tzinfo=timezone.utc)  # 14:59 Bogota
    assert resolve_world_date(now) == "2026-10-15"


def test_at_15_bogota_uses_next_day():
    now = datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc)  # 15:00 Bogota
    assert resolve_world_date(now) == "2026-10-16"


def test_evening_bogota_uses_next_day():
    now = datetime(2026, 10, 15, 23, 5, tzinfo=timezone.utc)  # 18:05 Bogota
    assert resolve_world_date(now) == "2026-10-16"


def test_naive_time_rejected():
    with pytest.raises(ValueError, match="NOW_MUST_BE_TIMEZONE_AWARE"):
        resolve_world_date(datetime(2026, 10, 15, 18, 0))
