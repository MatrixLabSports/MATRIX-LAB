from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SUPERVISOR = Path("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
OUT = Path("evidence/market_portfolio/MATRIX_BLOCKED_MARKET_ACTIVATION_PLAN_LAST.json")

PRIORITY_ORDER = {
    "TEAM_TOTAL_GOALS_HOME": 1,
    "TEAM_TOTAL_GOALS_AWAY": 2,
    "DOUBLE_CHANCE_12": 3,
    "ASIAN_OR_EUROPEAN_HANDICAP": 4,
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER": 5,
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER": 6,
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME": 7,
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY": 8,
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME": 9,
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY": 10,
    "ACES": 11,
    "DOUBLE_FAULTS": 12,
    "BREAKS_OF_SERVE": 13,
}
