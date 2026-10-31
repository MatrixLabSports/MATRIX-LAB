from tools import api_football_prospective_daily_cycle as daily
from tools import api_football_team_last_fallback as fallback


def test_daily_api_reserve_is_operational_and_conservative():
    # The reserve must protect several full governed cycles, but must not consume
    # almost the entire paid daily allowance before work can start.
    cycle_budget = daily.GROUP_HISTORY_MAX_REQUESTS + daily.TEAM_LAST_MAX_REQUESTS
    assert daily.DAILY_REMAINING_RESERVE == 1500
    assert fallback.MIN_DAILY_REMAINING_RESERVE == 1500
    assert daily.DAILY_REMAINING_RESERVE >= 5 * cycle_budget
    assert daily.DAILY_REMAINING_RESERVE <= 10 * cycle_budget
