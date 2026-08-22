from datetime import datetime, timedelta, timezone

import pytest

from app.application.football.live_odds_movement import (
    LiveOddsObservation,
    calculate_live_odds_movement,
    summarize_cross_book_movements,
)


NOW = datetime(
    2026, 8, 22, 19, 0,
    tzinfo=timezone.utc,
)


def observation(
    odds,
    *,
    bookmaker="book-a",
    at=NOW,
):
    return LiveOddsObservation(
        provider="provider-a",
        bookmaker=bookmaker,
        fixture_id="100",
        market_key="match_winner",
        selection_key="away",
        captured_at=at,
        decimal_odds=odds,
    )


def test_steam_and_velocity_are_time_aware():
    previous = observation(2.00)
    current = observation(
        1.80,
        at=NOW + timedelta(minutes=2),
    )
    movement = calculate_live_odds_movement(
        previous,
        current,
    )
    assert movement.direction == "STEAM"
    assert movement.change_pct == pytest.approx(10.0)
    assert (
        movement.velocity_pct_per_minute
        == pytest.approx(5.0)
    )
    assert movement.implied_probability_delta > 0


def test_drift_is_negative_change_pct():
    movement = calculate_live_odds_movement(
        observation(1.80),
        observation(
            2.00,
            at=NOW + timedelta(minutes=1),
        ),
    )
    assert movement.direction == "DRIFT"
    assert movement.change_pct < 0


def test_cross_book_requires_independent_books():
    one = calculate_live_odds_movement(
        observation(2.0, bookmaker="a"),
        observation(
            1.9,
            bookmaker="a",
            at=NOW + timedelta(minutes=1),
        ),
    )
    two = calculate_live_odds_movement(
        observation(2.1, bookmaker="b"),
        observation(
            2.0,
            bookmaker="b",
            at=NOW + timedelta(minutes=1),
        ),
    )
    summary = summarize_cross_book_movements(
        [one, two]
    )
    assert summary.direction == "STEAM"
    assert summary.steam_count == 2
