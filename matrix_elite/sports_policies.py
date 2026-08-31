from __future__ import annotations
from dataclasses import dataclass

FOOTBALL_ANALYSIS_ORDER=(
    "INDIVIDUAL_PLAYER",
    "PLAYER_UNITS",
    "COLLECTIVE_STRUCTURE",
    "MATCHUP",
    "CONTEXT",
    "MARKET_PROBABILITY",
    "ODDS_EV",
)
LIVE_STATES={"DISCARD","WATCH","PRE_SIGNAL","ENTRY","WINDOW_CLOSED"}
TENNIS_REQUIRED_HISTORY_WINDOWS=(5,10,20,30,50)

@dataclass(frozen=True)
class SimpleBetAdmission:
    decimal_odds: float
    expected_value: float
    data_quality_pass: bool
    calibration_pass: bool
    risk_pass: bool
    below_default_odds_floor_override_reason: str | None = None

    def admissible(self, *, default_odds_floor: float=1.70) -> bool:
        if self.decimal_odds <= 1.0:
            return False
        if self.expected_value <= 0:
            return False
        if not (self.data_quality_pass and self.calibration_pass and self.risk_pass):
            return False
        if self.decimal_odds < default_odds_floor and not self.below_default_odds_floor_override_reason:
            return False
        return True

@dataclass(frozen=True)
class CombinationAdmission:
    legs: int
    joint_probability: float | None
    dependency_controlled: bool
    joint_ev: float | None

    def admissible(self) -> bool:
        if self.legs < 2:
            return False
        if self.joint_probability is None or not 0 <= self.joint_probability <= 1:
            return False
        if not self.dependency_controlled:
            return False
        if self.joint_ev is None or self.joint_ev <= 0:
            return False
        return True


def combination_frequency_ok(*, simple_bets: int, combination_bets: int, maximum_share: float=0.10) -> bool:
    if simple_bets < 0 or combination_bets < 0 or not 0 <= maximum_share <= 1:
        raise ValueError("BET_FREQUENCY_INPUT_INVALID")
    total=simple_bets+combination_bets
    if total == 0:
        return True
    return combination_bets/total <= maximum_share + 1e-12


def validate_live_state(state: str) -> str:
    if state not in LIVE_STATES:
        raise ValueError("LIVE_STATE_INVALID")
    return state


def validate_tennis_feature_context(*, history_windows: tuple[int,...], injury_claim: bool, injury_verified: bool) -> None:
    if tuple(history_windows) != TENNIS_REQUIRED_HISTORY_WINDOWS:
        raise ValueError("TENNIS_HISTORY_WINDOWS_CONTRACT_VIOLATION")
    if injury_claim and not injury_verified:
        raise ValueError("UNVERIFIED_INJURY_INFERENCE_FORBIDDEN")
