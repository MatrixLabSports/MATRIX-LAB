from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.point_in_time_history import (
    build_point_in_time_history,
)


UTC = timezone.utc


def event(
    *,
    key,
    day,
    available_day=None,
    season="2026",
    completed=True,
    fingerprint_char="a",
):
    if available_day is None:
        available_day = day

    return SimpleNamespace(
        event_key=key,
        event_at=datetime(
            2026,
            8,
            day,
            10,
            tzinfo=UTC,
        ),
        season_key=season,
        completed=completed,
        source_available_at=datetime(
            2026,
            8,
            available_day,
            12,
            tzinfo=UTC,
        ),
        source_record_fingerprint=(
            fingerprint_char * 64
        ),
        event_fingerprint=(
            fingerprint_char * 63
            + hex(day % 16)[2:]
        ),
    )


def test_windows_5_10_20_30_50_are_supported():
    events = [
        event(
            key=f"MATCH:{day}",
            day=day,
            fingerprint_char=hex(day % 16)[2:],
        )
        for day in range(1, 21)
    ]

    history = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:test",
        events=events,
        as_of=datetime(2026, 8, 25, tzinfo=UTC),
        season_key="2026",
    )

    assert len(history.window(5)) == 5
    assert len(history.window(10)) == 10
    assert len(history.window(20)) == 20
    assert len(history.window(30)) == 20
    assert len(history.window(50)) == 20
    assert len(history.season) == 20
    assert len(history.career) == 20


def test_future_events_are_excluded():
    events = (
        event(key="PAST", day=5),
        event(key="FUTURE", day=20),
    )

    history = build_point_in_time_history(
        sport="football",
        canonical_id="football:team:test",
        events=events,
        as_of=datetime(2026, 8, 10, tzinfo=UTC),
        season_key="2026",
    )

    assert tuple(
        item.event_key
        for item in history.career
    ) == ("PAST",)


def test_unavailable_correction_is_not_visible_yet():
    original = event(
        key="MATCH:1",
        day=1,
        available_day=2,
        fingerprint_char="a",
    )
    correction = event(
        key="MATCH:1",
        day=1,
        available_day=8,
        fingerprint_char="b",
    )

    before = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:test",
        events=(original, correction),
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        season_key="2026",
    )
    after = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:test",
        events=(original, correction),
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
        season_key="2026",
    )

    assert (
        before.career[0].event_fingerprint
        == original.event_fingerprint
    )
    assert (
        after.career[0].event_fingerprint
        == correction.event_fingerprint
    )


def test_same_time_conflicting_corrections_fail_closed():
    first = event(
        key="MATCH:1",
        day=1,
        available_day=2,
        fingerprint_char="a",
    )
    second = event(
        key="MATCH:1",
        day=1,
        available_day=2,
        fingerprint_char="b",
    )

    with pytest.raises(
        ValueError,
        match="AMBIGUOUS_HISTORY_CORRECTION_AS_OF",
    ):
        build_point_in_time_history(
            sport="football",
            canonical_id="football:team:test",
            events=(first, second),
            as_of=datetime(2026, 8, 5, tzinfo=UTC),
            season_key="2026",
        )


def test_incomplete_events_are_excluded():
    history = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:test",
        events=(
            event(
                key="DONE",
                day=1,
                completed=True,
            ),
            event(
                key="LIVE",
                day=2,
                completed=False,
            ),
        ),
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        season_key="2026",
    )

    assert tuple(
        item.event_key
        for item in history.career
    ) == ("DONE",)
