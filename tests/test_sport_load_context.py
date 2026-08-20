from datetime import datetime, timezone

import pytest

from app.application.football.sport_load_context import (
    build_football_load_context,
)
from app.application.tennis.sport_load_context import (
    build_tennis_load_context,
)


UTC = timezone.utc


def kwargs():
    return dict(
        canonical_id="subject",
        as_of=datetime(2026, 8, 10, 12, tzinfo=UTC),
        event_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        available_at=datetime(2026, 8, 10, 10, tzinfo=UTC),
        previous_event_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        travel_km=800.0,
        timezone_shift_hours=1.0,
        altitude_delta_m=1200.0,
        matches_last_7d=2,
        matches_last_14d=4,
        cumulative_minutes_last_7d=180.0,
        cumulative_minutes_last_14d=360.0,
    )


def test_tennis_context_computes_rest_without_fatigue_score():
    context = build_tennis_load_context(**kwargs())

    assert context.sport == "tennis"
    assert context.rest_hours == 72.0
    assert context.payload()["fatigue_score_computed"] is False


def test_football_context_remains_sport_separate():
    context = build_football_load_context(**kwargs())

    assert context.sport == "football"
    assert context.context_fingerprint != build_tennis_load_context(
        **kwargs()
    ).context_fingerprint


def test_future_unavailable_context_is_rejected():
    values = kwargs()
    values["available_at"] = datetime(
        2026, 8, 10, 13, tzinfo=UTC
    )

    with pytest.raises(
        ValueError,
        match="CONTEXT_NOT_AVAILABLE_AS_OF",
    ):
        build_tennis_load_context(**values)


def test_window_counts_must_be_consistent():
    values = kwargs()
    values["matches_last_7d"] = 5
    values["matches_last_14d"] = 4

    with pytest.raises(
        ValueError,
        match="MATCH_COUNT_WINDOW_INCONSISTENCY",
    ):
        build_football_load_context(**values)


def test_missing_travel_is_preserved_not_zero():
    values = kwargs()
    values["travel_km"] = None

    context = build_tennis_load_context(**values)

    assert context.travel_km is None
    assert context.payload()["missing_is_zero"] is False
