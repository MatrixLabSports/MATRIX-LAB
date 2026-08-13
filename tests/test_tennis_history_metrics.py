from app.sports.tennis.history_metrics import win_rate
from app.sports.tennis.historical_match import TennisHistoricalMatch


def _match(won: bool) -> TennisHistoricalMatch:
    return TennisHistoricalMatch(
        player="Carlos Alcaraz",
        opponent="Test Opponent",
        date="2026-08-10",
        tournament="Test Tournament",
        surface="Hard",
        won=won,
        sets_won=2 if won else 1,
        sets_lost=1 if won else 2,
        games_won=18 if won else 14,
        games_lost=14 if won else 18,
    )


def test_win_rate_calculates_percentage_of_wins():
    matches = (
        _match(True),
        _match(True),
        _match(False),
        _match(True),
    )

    assert win_rate(matches) == 75.0