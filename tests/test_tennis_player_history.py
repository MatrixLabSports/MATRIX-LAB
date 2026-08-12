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