from datetime import datetime, timezone
from types import SimpleNamespace

from app.application.tennis.professional_history_profile import (
    build_tennis_history_profile,
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
    surface="hard",
    indoor=False,
    season="2026",
    competition="ATP:TEST",
    metrics=None,
):
    if metrics is None:
        metrics = {
            "aces": day,
            "hold_pct": 80.0,
            "return_points_won_pct": 35.0,
        }

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
        opponent_canonical_id=f"tennis:player:{day}",
        outcome=outcome,
        completed=True,
        retirement=False,
        surface=surface,
        indoor=indoor,
        metrics=metrics,
        source_record_fingerprint=(
            hex(day % 16)[2:] * 64
        ),
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
            outcome="W" if day % 2 else "L",
            surface="hard" if day <= 7 else "clay",
            indoor=day <= 3,
        )
        for day in range(1, 11)
    )

    return build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:subject",
        events=events,
        as_of=datetime(2026, 8, 15, tzinfo=UTC),
        season_key="2026",
    )


def test_tennis_profile_has_5_10_20_30_50_windows():
    profile = build_tennis_history_profile(
        history=history(),
        target_surface="hard",
        target_indoor=True,
    )

    overall = profile.segments["overall"]

    assert overall["windows"]["5"]["sample_size"] == 5
    assert overall["windows"]["10"]["sample_size"] == 10
    assert overall["windows"]["20"]["sample_size"] == 10
    assert overall["windows"]["30"]["sample_size"] == 10
    assert overall["windows"]["50"]["sample_size"] == 10


def test_tennis_profile_segments_surface_and_environment():
    profile = build_tennis_history_profile(
        history=history(),
        target_surface="hard",
        target_indoor=True,
    )

    hard = profile.segments["surface:hard"]
    indoor = profile.segments["environment:indoor"]

    assert hard["career"]["sample_size"] == 7
    assert indoor["career"]["sample_size"] == 3


def test_tennis_metric_coverage_preserves_missing():
    value = event(
        key="M:1",
        day=1,
        outcome="W",
        metrics={
            "aces": None,
            "hold_pct": 80.0,
        },
    )
    h = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:subject",
        events=(value,),
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        season_key="2026",
    )

    profile = build_tennis_history_profile(
        history=h
    )

    summary = profile.segments["overall"]["career"]

    assert summary["metric_means"]["aces"] is None
    assert summary["metric_coverage"]["aces"] == 0
    assert summary["metric_coverage"]["hold_pct"] == 1


def test_tennis_profile_does_not_apply_arbitrary_recency_weights():
    profile = build_tennis_history_profile(
        history=history()
    )

    assert profile.payload()[
        "recency_weighting_applied"
    ] is False
