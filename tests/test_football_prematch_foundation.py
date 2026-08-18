from datetime import datetime, timedelta, timezone

import pytest

from app.research.football.prematch import (
    HistoricalFixtureOutcome,
    PrematchFeaturePolicy,
    build_prematch_research_rows,
)


def outcome(fid, kickoff, home, away, hg, ag, competition="Liga"):
    return HistoricalFixtureOutcome(
        fixture_id=str(fid), kickoff_utc=kickoff, home_team=home, away_team=away,
        competition=competition, country="Colombia", season=2026,
        home_goals=hg, away_goals=ag,
    )


def make_schedule(count=30):
    start = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        dt = start + timedelta(days=index * 3)
        if index % 2 == 0:
            rows.append(outcome(index, dt.isoformat(), "A", "B", 2, 1))
        else:
            rows.append(outcome(index, dt.isoformat(), "B", "A", 1, 1))
    return rows


def test_prematch_features_are_leakage_safe_and_use_prior_matches_only():
    rows = build_prematch_research_rows(
        make_schedule(),
        policy=PrematchFeaturePolicy(windows=(5, 10, 20), min_prior_matches=5, result_availability_buffer_hours=6),
    )
    assert rows
    first = rows[0]
    assert first.features["home_prior_matches"] >= 5
    assert first.features["away_prior_matches"] >= 5
    assert first.label_observed_at_utc > first.as_of_utc


def test_prematch_builder_is_order_invariant():
    schedule = make_schedule()
    policy = PrematchFeaturePolicy(windows=(5, 10), min_prior_matches=5)
    a = build_prematch_research_rows(schedule, policy=policy)
    b = build_prematch_research_rows(reversed(schedule), policy=policy)
    assert [(row.fixture_id, row.features) for row in a] == [(row.fixture_id, row.features) for row in b]


def test_same_time_match_is_not_used_as_prior_history():
    kickoff = "2026-02-01T15:00:00+00:00"
    rows = build_prematch_research_rows(
        [outcome("x", kickoff, "A", "C", 5, 0), outcome("y", kickoff, "C", "B", 0, 5)],
        policy=PrematchFeaturePolicy(windows=(5,), min_prior_matches=0, result_availability_buffer_hours=6),
    )
    by_id = {row.fixture_id: row for row in rows}
    assert by_id["y"].features["home_prior_matches"] == 0


def test_context_and_competition_features_are_separate():
    rows = build_prematch_research_rows(
        make_schedule(),
        policy=PrematchFeaturePolicy(windows=(5,), min_prior_matches=5),
    )
    row = rows[-1]
    assert "home_context_last_5_points_per_match" in row.features
    assert "away_context_last_5_points_per_match" in row.features
    assert "home_comp_last_5_points_per_match" in row.features
    assert "away_comp_last_5_points_per_match" in row.features


def test_stable_provider_ids_preserve_history_across_name_changes():
    t0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    first = HistoricalFixtureOutcome(
        fixture_id="1", kickoff_utc=t0.isoformat(), home_team="Club Old Name", away_team="B",
        competition="Liga", country="Colombia", season=2026, home_goals=2, away_goals=0,
        home_team_external_id="100", away_team_external_id="200", competition_external_id="50",
    )
    second = HistoricalFixtureOutcome(
        fixture_id="2", kickoff_utc=(t0 + timedelta(days=10)).isoformat(), home_team="Club New Name", away_team="B",
        competition="Liga Renamed", country="Colombia", season=2026, home_goals=1, away_goals=1,
        home_team_external_id="100", away_team_external_id="200", competition_external_id="50",
    )
    rows = build_prematch_research_rows(
        [first, second],
        policy=PrematchFeaturePolicy(windows=(5,), min_prior_matches=1, result_availability_buffer_hours=1),
    )
    assert len(rows) == 1
    assert rows[0].features["home_prior_matches"] == 1
    assert rows[0].features["home_comp_last_5_matches"] == 1


def test_policy_rejects_duplicate_windows():
    with pytest.raises(ValueError):
        PrematchFeaturePolicy(windows=(5, 5))
