import pytest

from app.sports.tennis.historical_match import TennisHistoricalMatch


def test_tennis_historical_match_can_be_created():
    match = TennisHistoricalMatch(
        player="Carlos Alcaraz",
        opponent="Jannik Sinner",
        date="2026-08-10",
        tournament="Test Tournament",
        surface="Hard",
        won=True,
        sets_won=2,
        sets_lost=1,
        games_won=18,
        games_lost=14,
    )

    assert match.player == "Carlos Alcaraz"
    assert match.opponent == "Jannik Sinner"
    assert match.won is True


def test_tennis_historical_match_rejects_same_player():
    with pytest.raises(ValueError):
        TennisHistoricalMatch(
            player="Carlos Alcaraz",
            opponent="Carlos Alcaraz",
            date="2026-08-10",
            tournament="Test Tournament",
            surface="Hard",
            won=True,
            sets_won=2,
            sets_lost=0,
            games_won=12,
            games_lost=4,
        )