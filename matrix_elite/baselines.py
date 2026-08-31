from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Mapping, Sequence

from .metrics import brier_score, log_loss

_EPS = 1e-15


FOOTBALL_MARKETS = frozenset({
    "1X2",
    "DOUBLE_CHANCE",
    "TOTALS",
    "BTTS",
    "CORNERS",
    "CARDS",
    "PLAYER_SHOTS",
})
TENNIS_MARKETS = frozenset({
    "MATCH_WINNER",
    "SET_WINNER",
    "TOTAL_GAMES",
    "HANDICAP",
    "TIE_BREAK",
    "BREAK_MARKETS",
    "LIVE_SET_GAME",
})
MARKETS_BY_SPORT = {"football": FOOTBALL_MARKETS, "tennis": TENNIS_MARKETS}


@dataclass(frozen=True)
class BaselineInputEvidence:
    sport: str
    market: str
    pit_snapshot_sha256: str
    identity_manifest_sha256: str
    rights_gate_passed: bool
    train_n: int
    validation_n: int

    def __post_init__(self) -> None:
        if self.sport not in MARKETS_BY_SPORT:
            raise ValueError("SPORT_NOT_REGISTERED")
        if self.market not in MARKETS_BY_SPORT[self.sport]:
            raise ValueError("MARKET_NOT_REGISTERED_FOR_SPORT")
        for name in ("pit_snapshot_sha256", "identity_manifest_sha256"):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name.upper()}_REQUIRED")
            int(value, 16)
        if not self.rights_gate_passed:
            raise ValueError("RIGHTS_GATE_REQUIRED")
        if type(self.train_n) is not int or type(self.validation_n) is not int or self.train_n < 1 or self.validation_n < 1:
            raise ValueError("BASELINE_SAMPLE_SIZE_INVALID")


@dataclass(frozen=True)
class BinaryBaselineEvidence:
    empirical_probability: float
    empirical_brier: float
    empirical_log_loss: float
    market_brier: float
    market_log_loss: float
    n: int


@dataclass(frozen=True)
class MulticlassBaselineEvidence:
    labels: tuple[str, ...]
    empirical_probabilities: tuple[float, ...]
    empirical_brier: float
    empirical_log_loss: float
    market_brier: float
    market_log_loss: float
    n: int


def require_registered_market(sport: str, market: str) -> None:
    if sport not in MARKETS_BY_SPORT:
        raise ValueError("SPORT_NOT_REGISTERED")
    if market not in MARKETS_BY_SPORT[sport]:
        raise ValueError("MARKET_NOT_REGISTERED_FOR_SPORT")


def _binary_outcomes(outcomes: Sequence[int]) -> tuple[int, ...]:
    vals = tuple(int(x) for x in outcomes)
    if not vals or any(x not in (0, 1) for x in vals):
        raise ValueError("BINARY_OUTCOMES_REQUIRED")
    return vals


def fit_binary_empirical_baseline(
    train_outcomes: Sequence[int],
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> float:
    y = _binary_outcomes(train_outcomes)
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("BETA_PRIOR_MUST_BE_POSITIVE")
    return (sum(y) + prior_alpha) / (len(y) + prior_alpha + prior_beta)


def binary_baseline_benchmark(
    *,
    train_outcomes: Sequence[int],
    validation_outcomes: Sequence[int],
    validation_market_probabilities: Sequence[float],
) -> BinaryBaselineEvidence:
    train = _binary_outcomes(train_outcomes)
    val = _binary_outcomes(validation_outcomes)
    if len(val) != len(validation_market_probabilities):
        raise ValueError("VALIDATION_MARKET_LENGTH_MISMATCH")
    p = fit_binary_empirical_baseline(train)
    empirical = [p] * len(val)
    return BinaryBaselineEvidence(
        empirical_probability=p,
        empirical_brier=brier_score(empirical, val),
        empirical_log_loss=log_loss(empirical, val),
        market_brier=brier_score(validation_market_probabilities, val),
        market_log_loss=log_loss(validation_market_probabilities, val),
        n=len(val),
    )


def _normalize_probabilities(row: Sequence[float], n_labels: int) -> tuple[float, ...]:
    if len(row) != n_labels:
        raise ValueError("MULTICLASS_PROBABILITY_WIDTH_MISMATCH")
    vals = tuple(float(x) for x in row)
    if any(x < 0 or x > 1 for x in vals):
        raise ValueError("MULTICLASS_PROBABILITY_OUT_OF_RANGE")
    total = sum(vals)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("MULTICLASS_PROBABILITIES_MUST_SUM_TO_ONE")
    return tuple(min(max(x, _EPS), 1 - _EPS) for x in vals)


def fit_multiclass_empirical_baseline(
    train_labels: Sequence[str],
    *,
    labels: Sequence[str],
    prior: float = 1.0,
) -> tuple[float, ...]:
    labels = tuple(labels)
    if len(labels) < 2 or len(set(labels)) != len(labels):
        raise ValueError("MULTICLASS_LABELS_INVALID")
    if prior <= 0:
        raise ValueError("DIRICHLET_PRIOR_MUST_BE_POSITIVE")
    counts = {label: 0 for label in labels}
    if not train_labels:
        raise ValueError("TRAIN_LABELS_REQUIRED")
    for y in train_labels:
        if y not in counts:
            raise ValueError("UNKNOWN_TRAIN_LABEL")
        counts[y] += 1
    denom = len(train_labels) + prior * len(labels)
    return tuple((counts[label] + prior) / denom for label in labels)


def multiclass_brier_score(
    probabilities: Sequence[Sequence[float]],
    outcomes: Sequence[str],
    *,
    labels: Sequence[str],
) -> float:
    labels = tuple(labels)
    if len(probabilities) != len(outcomes) or not outcomes:
        raise ValueError("MULTICLASS_LENGTH_MISMATCH_OR_EMPTY")
    index = {label: i for i, label in enumerate(labels)}
    if len(index) != len(labels):
        raise ValueError("MULTICLASS_LABELS_INVALID")
    total = 0.0
    for row, y in zip(probabilities, outcomes):
        if y not in index:
            raise ValueError("UNKNOWN_OUTCOME_LABEL")
        p = _normalize_probabilities(row, len(labels))
        yi = index[y]
        total += sum((prob - (1.0 if i == yi else 0.0)) ** 2 for i, prob in enumerate(p))
    return total / len(outcomes)


def multiclass_log_loss(
    probabilities: Sequence[Sequence[float]],
    outcomes: Sequence[str],
    *,
    labels: Sequence[str],
) -> float:
    labels = tuple(labels)
    if len(probabilities) != len(outcomes) or not outcomes:
        raise ValueError("MULTICLASS_LENGTH_MISMATCH_OR_EMPTY")
    index = {label: i for i, label in enumerate(labels)}
    if len(index) != len(labels):
        raise ValueError("MULTICLASS_LABELS_INVALID")
    total = 0.0
    for row, y in zip(probabilities, outcomes):
        if y not in index:
            raise ValueError("UNKNOWN_OUTCOME_LABEL")
        p = _normalize_probabilities(row, len(labels))
        total -= log(p[index[y]])
    return total / len(outcomes)


def multiclass_baseline_benchmark(
    *,
    train_outcomes: Sequence[str],
    validation_outcomes: Sequence[str],
    validation_market_probabilities: Sequence[Sequence[float]],
    labels: Sequence[str],
) -> MulticlassBaselineEvidence:
    labels = tuple(labels)
    if len(validation_outcomes) != len(validation_market_probabilities):
        raise ValueError("VALIDATION_MARKET_LENGTH_MISMATCH")
    empirical = fit_multiclass_empirical_baseline(train_outcomes, labels=labels)
    empirical_rows = [empirical] * len(validation_outcomes)
    return MulticlassBaselineEvidence(
        labels=labels,
        empirical_probabilities=empirical,
        empirical_brier=multiclass_brier_score(empirical_rows, validation_outcomes, labels=labels),
        empirical_log_loss=multiclass_log_loss(empirical_rows, validation_outcomes, labels=labels),
        market_brier=multiclass_brier_score(validation_market_probabilities, validation_outcomes, labels=labels),
        market_log_loss=multiclass_log_loss(validation_market_probabilities, validation_outcomes, labels=labels),
        n=len(validation_outcomes),
    )


def sample_size_gate(*, train_n: int, validation_n: int, minimum_train: int, minimum_validation: int) -> bool:
    values = (train_n, validation_n, minimum_train, minimum_validation)
    if any(type(x) is not int or x < 1 for x in values):
        raise ValueError("SAMPLE_SIZE_GATE_INVALID")
    return train_n >= minimum_train and validation_n >= minimum_validation


def segment_stability_gate(
    segment_improvements: Mapping[str, tuple[int, float, float]],
    *,
    minimum_segment_n: int,
    minimum_positive_segment_fraction: float = 0.75,
) -> dict[str, float | int | bool]:
    """Each segment value is (n, brier_improvement, log_loss_improvement)."""
    if minimum_segment_n < 1 or not 0 < minimum_positive_segment_fraction <= 1:
        raise ValueError("SEGMENT_GATE_CONFIGURATION_INVALID")
    if not segment_improvements:
        raise ValueError("SEGMENTS_REQUIRED")
    eligible = 0
    positive = 0
    underpowered = 0
    for n, brier_imp, log_imp in segment_improvements.values():
        if n < minimum_segment_n:
            underpowered += 1
            continue
        eligible += 1
        if brier_imp > 0 and log_imp > 0:
            positive += 1
    fraction = (positive / eligible) if eligible else 0.0
    return {
        "segments_total": len(segment_improvements),
        "segments_eligible": eligible,
        "segments_underpowered": underpowered,
        "positive_segments": positive,
        "positive_fraction": fraction,
        "pass": eligible > 0 and fraction >= minimum_positive_segment_fraction,
    }
