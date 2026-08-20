from datetime import datetime, timezone
from types import SimpleNamespace

from app.application.football.professional_history_profile import (
    build_football_history_profile,
)
from app.core.point_in_time_history import (
    build_point_in_time_history,
)


UTC = timezone.utc


def event(
    *,
    key,
    day,
    outcome,
    venue="home",
    season="2026",
    competition="LEAGUE:TEST",
    metrics=None,
):
    if metrics is None:
        metrics = {
            "goals_for": 2,
            "goals_against": 1,
            "xg_for": 1.5,
            "xg_against": 0.9,
            "corners_for": 6,
            "first_half_corners_for": 3,
        }

    char = hex(day % 16)[2:]

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
        competition_key=competition,
        opponent_canonical_id=f"football:team:{day}",
        outcome=outcome,
        completed=True,
        venue=venue,
        metrics=metrics,
        source_record_fingerprint=char * 64,
        source_available_at=datetime(
            2026,
            8,
            day,
            12,
            tzinfo=UTC,
        ),
        event_fingerprint=(
            hex((day + 1) % 16)[2:] * 64
        ),
    )


def history():
    events = tuple(
        event(
            key=f"M:{day}",
            day=day,
            outcome=(
                "W"
                if day % 3 == 1
                else "D"
                if day % 3 == 2
                else "L"
            ),
            venue="home" if day <= 6 else "away",
        )
        for day in range(1, 11)
    )

    return build_point_in_time_history(
        sport="football",
        canonical_id="football:team:subject",
        events=events,
        as_of=datetime(2026, 8, 15, tzinfo=UTC),
        season_key="2026",
    )


def test_football_profile_has_5_10_20_30_50_windows():
    profile = build_football_history_profile(
        history=history(),
        target_venue="home",
    )

    overall = profile.segments["overall"]

    assert overall["windows"]["5"]["sample_size"] == 5
    assert overall["windows"]["10"]["sample_size"] == 10
    assert overall["windows"]["20"]["sample_size"] == 10
    assert overall["windows"]["30"]["sample_size"] == 10
    assert overall["windows"]["50"]["sample_size"] == 10


def test_football_profile_segments_home_away():
    profile = build_football_history_profile(
        history=history(),
        target_venue="home",
    )

    home = profile.segments["venue:home"]

    assert home["career"]["sample_size"] == 6


def test_football_profile_includes_half_metrics():
    profile = build_football_history_profile(
        history=history()
    )

    summary = profile.segments["overall"]["career"]

    assert (
        summary["metric_coverage"][
            "first_half_corners_for"
        ]
        == 10
    )
    assert (
        summary["metric_means"][
            "first_half_corners_for"
        ]
        == 3.0
    )


def test_football_profile_keeps_sports_separate():
    tennis_like = SimpleNamespace(
        sport="tennis"
    )

    import pytest

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        build_football_history_profile(
            history=tennis_like
        )
