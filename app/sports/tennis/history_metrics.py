from app.sports.tennis.historical_match import TennisHistoricalMatch


def win_rate(
    matches: tuple[TennisHistoricalMatch, ...],
) -> float | None:
    if not matches:
        return None

    wins = sum(1 for match in matches if match.won)

    return wins / len(matches) * 100