from __future__ import annotations


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def resolve_odds_api_net_market_version(
    *,
    sport: str,
    bet_type: object,
    metric: object,
    period: object,
) -> str | None:
    sport_n = _norm(sport)
    bet_n = _norm(bet_type)
    metric_n = _norm(metric)
    period_n = _norm(period)

    if sport_n == "football":
        if bet_n in {"moneyline", "moneyline 3w"} and period_n in {"full time", "match", "full game"}:
            return "MATRIX-MARKET-R2/football/RESULT_OR_DOUBLE_CHANCE/result-or-double-chance"
        if bet_n == "both teams to score" and period_n in {"full time", "match", "full game"}:
            return "MATRIX-MARKET-R2/football/BOTH_TEAMS_TO_SCORE/yes-no"
        if bet_n == "total" and metric_n == "corners":
            return "MATRIX-MARKET-R2/football/CORNERS/total-corners"
        if bet_n == "total" and metric_n == "cards":
            return "MATRIX-MARKET-R2/football/CARDS/total-cards"
        if bet_n in {"total", "team total"} and metric_n in {"", "goals"}:
            return "MATRIX-MARKET-R2/football/GOAL_TOTALS_OR_TEAM_TOTALS/goal-total"
        if bet_n == "player prop" and metric_n in {"player shots", "player shots on target"}:
            return "MATRIX-MARKET-R2/football/PLAYER_SHOTS_OR_SHOTS_ON_TARGET/player-threshold"
        if bet_n == "player prop" and metric_n in {"player assists", "player passes"}:
            return "MATRIX-MARKET-R2/football/PLAYER_ASSISTS_OR_PASSES/player-threshold"
        return None

    if sport_n == "tennis":
        if bet_n in {"moneyline", "moneyline 3w"}:
            if "set" in period_n and period_n not in {"full time", "match", "full game"}:
                return "MATRIX-MARKET-R2/tennis/SET_WINNER/set-winner"
            if period_n in {"full time", "match", "full game"}:
                return "MATRIX-MARKET-R2/tennis/MATCH_WINNER/match-winner"
        if bet_n == "handicap" and metric_n == "games":
            return "MATRIX-MARKET-R2/tennis/GAME_HANDICAP/game-handicap"
        if bet_n in {"total", "team total"} and metric_n in {"games", "sets"}:
            return "MATRIX-MARKET-R2/tennis/GAME_OR_SET_TOTALS/game-or-set-total"
        if bet_n == "player prop" and metric_n in {
            "standard",
            "player performance",
            "player set wins",
            "player total games",
            "aces",
            "double faults",
        }:
            return "MATRIX-MARKET-R2/tennis/PLAYER_PROPS/player-threshold"
        return None

    return None
