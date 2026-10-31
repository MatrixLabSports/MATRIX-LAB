from app.market.odds_api_net_market_mapping import resolve_odds_api_net_market_version


def test_football_documented_market_mappings():
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="moneyline 3w", metric=None, period="full time"
    ) == "MATRIX-MARKET-R2/football/RESULT_OR_DOUBLE_CHANCE/result-or-double-chance"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="both teams to score", metric=None, period="full time"
    ) == "MATRIX-MARKET-R2/football/BOTH_TEAMS_TO_SCORE/yes-no"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="total", metric="corners", period="full time"
    ) == "MATRIX-MARKET-R2/football/CORNERS/total-corners"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="total", metric="cards", period="full time"
    ) == "MATRIX-MARKET-R2/football/CARDS/total-cards"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="total", metric="goals", period="full time"
    ) == "MATRIX-MARKET-R2/football/GOAL_TOTALS_OR_TEAM_TOTALS/goal-total"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="player prop", metric="player shots on target", period="full time"
    ) == "MATRIX-MARKET-R2/football/PLAYER_SHOTS_OR_SHOTS_ON_TARGET/player-threshold"
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="player prop", metric="player passes", period="full time"
    ) == "MATRIX-MARKET-R2/football/PLAYER_ASSISTS_OR_PASSES/player-threshold"


def test_tennis_documented_market_mappings():
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="moneyline", metric=None, period="full time"
    ) == "MATRIX-MARKET-R2/tennis/MATCH_WINNER/match-winner"
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="moneyline", metric=None, period="1st set"
    ) == "MATRIX-MARKET-R2/tennis/SET_WINNER/set-winner"
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="handicap", metric="games", period="full time"
    ) == "MATRIX-MARKET-R2/tennis/GAME_HANDICAP/game-handicap"
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="total", metric="games", period="full time"
    ) == "MATRIX-MARKET-R2/tennis/GAME_OR_SET_TOTALS/game-or-set-total"
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="player prop", metric="player total games", period="full time"
    ) == "MATRIX-MARKET-R2/tennis/PLAYER_PROPS/player-threshold"


def test_ambiguous_or_unsupported_market_fails_closed():
    assert resolve_odds_api_net_market_version(
        sport="football", bet_type="handicap", metric="goals", period="full time"
    ) is None
    assert resolve_odds_api_net_market_version(
        sport="tennis", bet_type="total", metric="tie breaks", period="full time"
    ) is None
    assert resolve_odds_api_net_market_version(
        sport="basketball", bet_type="moneyline", metric=None, period="full time"
    ) is None
