import pytest

from app.sports.tennis.historical_match import TennisHistoricalMatch
from app.sports.tennis.player_history import TennisPlayerHistory


def _match(
    date: str,
    opponent: str,
    won: bool,
) -> TennisHistoricalMatch:
    return TennisHistoricalMatch(
        player="Carlos Alcaraz",
        opponent=opponent,
        date=date,
        tournament="Test Tournament",
        surface="Hard",
        won=won,
        sets_won=2 if won else 1,
        sets_lost=1 if won else 2,
        games_won=18 if won else 14,
        games_lost=14 if won else 18,
    )


def test_player_history_can_be_created():
    history = TennisPlayerHistory(player="Carlos Alcaraz")

    assert history.player == "Carlos Alcaraz"
    assert history.matches == ()


def test_player_history_returns_most_recent_matches():
    history = TennisPlayerHistory(
        player="Carlos Alcaraz",
        matches=(
            _match("2026-08-01", "Player A", True),
            _match("2026-08-10", "Player B", False),
            _match("2026-08-05", "Player C", True),
        ),
    )

    recent = history.recent_matches(2)

    assert len(recent) == 2
    assert recent[0].date == "2026-08-10"
    assert recent[1].date == "2026-08-05"

@pytest.mark.parametrize("window_size", [5, 10, 20, 30, 50])
def test_player_history_supports_standard_windows(window_size):
    matches = tuple(
        _match(
            f"2026-07-{day:02d}",
            f"Player {day}",
            day % 2 == 0,
        )
        for day in range(1, 32)
    ) + tuple(
        _match(
            f"2026-06-{day:02d}",
            f"Previous Player {day}",
            day % 2 == 0,
        )
        for day in range(1, 20)
    )

    history = TennisPlayerHistory(
        player="Carlos Alcaraz",
        matches=matches,
    )

    window = history.window(window_size)

    assert len(window) == window_size


def test_player_history_window_returns_available_matches_when_history_is_short():
    history = TennisPlayerHistory(
        player="Carlos Alcaraz",
        matches=(
            _match("2026-08-10", "Player A", True),
            _match("2026-08-08", "Player B", False),
            _match("2026-08-05", "Player C", True),
        ),
    )

    window = history.window(20)

    assert len(window) == 3
    assert window[0].date == "2026-08-10"


def test_player_history_rejects_unsupported_window():
    history = TennisPlayerHistory(player="Carlos Alcaraz")

    with pytest.raises(ValueError):
        history.window(15)