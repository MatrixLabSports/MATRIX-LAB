from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, factorial
from typing import Iterable

from app.research.football.match_analysis_input import (
    FootballAnalysisReadiness,
    FootballAnalysisReadinessPolicy,
    FootballHistoryObservation,
    FootballMatchAnalysisInput,
    assess_match_analysis_readiness,
)


@dataclass(frozen=True)
class TransparentPoissonPolicy:
    max_history_per_team: int = 20
    score_cap: int = 10
    min_lambda: float = 0.05
    max_lambda: float = 5.0

    def __post_init__(self) -> None:
        if self.max_history_per_team < 1:
            raise ValueError("max_history_per_team must be positive")
        if self.score_cap < 5:
            raise ValueError("score_cap must be >= 5")
        if not 0 < self.min_lambda < self.max_lambda:
            raise ValueError("lambda bounds invalid")


@dataclass(frozen=True)
class ExperimentalFootballEvaluation:
    target_key: str
    fixture_id: str
    model_name: str
    model_status: str
    readiness: FootballAnalysisReadiness
    expected_home_goals: float | None
    expected_away_goals: float | None
    probabilities: dict[str, float] | None
    decision: str
    reasons: tuple[str, ...]
    input_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


def _mean(values: Iterable[int]) -> float:
    items = list(values)
    if not items:
        raise ValueError("mean requires observations")
    return sum(items) / len(items)


def _poisson(k: int, lam: float) -> float:
    return exp(-lam) * (lam ** k) / factorial(k)


def _score_probabilities(home_lambda: float, away_lambda: float, score_cap: int) -> dict[str, float]:
    home_win = draw = away_win = 0.0
    over_15 = over_25 = over_35 = btts = 0.0
    covered_mass = 0.0
    for home_goals in range(score_cap + 1):
        hp = _poisson(home_goals, home_lambda)
        for away_goals in range(score_cap + 1):
            p = hp * _poisson(away_goals, away_lambda)
            covered_mass += p
            if home_goals > away_goals:
                home_win += p
            elif home_goals == away_goals:
                draw += p
            else:
                away_win += p
            total = home_goals + away_goals
            over_15 += p if total >= 2 else 0.0
            over_25 += p if total >= 3 else 0.0
            over_35 += p if total >= 4 else 0.0
            btts += p if home_goals > 0 and away_goals > 0 else 0.0
    # score_cap=10 makes residual tiny for constrained lambdas, but normalize so 1X2 sums exactly.
    if covered_mass <= 0:
        raise ValueError("invalid Poisson mass")
    return {
        "home_win": home_win / covered_mass,
        "draw": draw / covered_mass,
        "away_win": away_win / covered_mass,
        "over_1_5": over_15 / covered_mass,
        "over_2_5": over_25 / covered_mass,
        "over_3_5": over_35 / covered_mass,
        "btts": btts / covered_mass,
    }


def evaluate_transparent_poisson_baseline(
    value: FootballMatchAnalysisInput,
    *,
    readiness_policy: FootballAnalysisReadinessPolicy = FootballAnalysisReadinessPolicy(),
    model_policy: TransparentPoissonPolicy = TransparentPoissonPolicy(),
) -> ExperimentalFootballEvaluation:
    readiness = assess_match_analysis_readiness(value, policy=readiness_policy)
    if not readiness.ready:
        return ExperimentalFootballEvaluation(
            target_key=value.target_key,
            fixture_id=value.fixture_id,
            model_name="transparent_poisson_baseline_v1",
            model_status="BLOCKED_INSUFFICIENT_DATA",
            readiness=readiness,
            expected_home_goals=None,
            expected_away_goals=None,
            probabilities=None,
            decision="NO_BET",
            reasons=("insufficient_pre_match_history",),
            input_sha256=value.canonical_sha256(),
        )

    home = value.home_history[: model_policy.max_history_per_team]
    away = value.away_history[: model_policy.max_history_per_team]
    home_gf = _mean(row.goals_for for row in home)
    home_ga = _mean(row.goals_against for row in home)
    away_gf = _mean(row.goals_for for row in away)
    away_ga = _mean(row.goals_against for row in away)
    home_lambda = min(model_policy.max_lambda, max(model_policy.min_lambda, (home_gf + away_ga) / 2.0))
    away_lambda = min(model_policy.max_lambda, max(model_policy.min_lambda, (away_gf + home_ga) / 2.0))
    probabilities = _score_probabilities(home_lambda, away_lambda, model_policy.score_cap)

    return ExperimentalFootballEvaluation(
        target_key=value.target_key,
        fixture_id=value.fixture_id,
        model_name="transparent_poisson_baseline_v1",
        model_status="EXPERIMENTAL_NOT_PROMOTED",
        readiness=readiness,
        expected_home_goals=round(home_lambda, 6),
        expected_away_goals=round(away_lambda, 6),
        probabilities={key: round(number, 8) for key, number in probabilities.items()},
        # Deliberately not allowed to recommend money: validation/promotion gates remain open.
        decision="NO_BET",
        reasons=("baseline_only", "not_calibrated", "odds_ev_not_validated", "paper_trading_incomplete"),
        input_sha256=value.canonical_sha256(),
    )
