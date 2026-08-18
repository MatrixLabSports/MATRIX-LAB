from __future__ import annotations

from dataclasses import dataclass
from math import log
from random import Random
from typing import Iterable


def _probability(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("probabilities must be numeric")
    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError("probabilities must be between 0 and 1")
    return value


def _binary_log_loss(probability: float, outcome: bool) -> float:
    eps = 1e-15
    p = min(max(probability, eps), 1 - eps)
    return -(log(p) if outcome else log(1 - p))


@dataclass(frozen=True)
class PairedPrediction:
    fixture_id: str
    block_id: str
    outcome: bool
    candidate_probability: float
    baseline_probability: float

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not self.block_id.strip():
            raise ValueError("fixture_id and block_id are required")
        if not isinstance(self.outcome, bool):
            raise ValueError("outcome must be bool")
        object.__setattr__(self, "candidate_probability", _probability(self.candidate_probability))
        object.__setattr__(self, "baseline_probability", _probability(self.baseline_probability))


@dataclass(frozen=True)
class PairedModelComparison:
    sample_size: int
    block_count: int
    candidate_brier: float
    baseline_brier: float
    brier_delta: float
    brier_delta_ci_low: float
    brier_delta_ci_high: float
    candidate_log_loss: float
    baseline_log_loss: float
    log_loss_delta: float
    log_loss_delta_ci_low: float
    log_loss_delta_ci_high: float

    @property
    def candidate_beats_baseline_with_brier_confidence(self) -> bool:
        return self.brier_delta_ci_high < 0

    @property
    def candidate_beats_baseline_with_logloss_confidence(self) -> bool:
        return self.log_loss_delta_ci_high < 0


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute quantile of empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _metric_deltas(rows: list[PairedPrediction]) -> tuple[float, float]:
    candidate_brier = sum((row.candidate_probability - float(row.outcome)) ** 2 for row in rows) / len(rows)
    baseline_brier = sum((row.baseline_probability - float(row.outcome)) ** 2 for row in rows) / len(rows)
    candidate_log = sum(_binary_log_loss(row.candidate_probability, row.outcome) for row in rows) / len(rows)
    baseline_log = sum(_binary_log_loss(row.baseline_probability, row.outcome) for row in rows) / len(rows)
    return candidate_brier - baseline_brier, candidate_log - baseline_log


def compare_candidate_to_baseline(
    predictions: Iterable[PairedPrediction],
    *,
    bootstrap_iterations: int = 2000,
    confidence_level: float = 0.95,
    random_seed: int = 20260730,
) -> PairedModelComparison:
    rows = list(predictions)
    if not rows:
        raise ValueError("comparison requires predictions")
    if len({row.fixture_id for row in rows}) != len(rows):
        raise ValueError("comparison requires one prediction per fixture")
    if isinstance(bootstrap_iterations, bool) or not isinstance(bootstrap_iterations, int) or bootstrap_iterations < 100:
        raise ValueError("bootstrap_iterations must be an integer >= 100")
    if not 0.5 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0.5 and 1")

    blocks: dict[str, list[PairedPrediction]] = {}
    for row in rows:
        blocks.setdefault(row.block_id, []).append(row)
    block_ids = sorted(blocks)
    if len(block_ids) < 2:
        raise ValueError("block bootstrap requires at least two blocks")

    candidate_brier = sum((row.candidate_probability - float(row.outcome)) ** 2 for row in rows) / len(rows)
    baseline_brier = sum((row.baseline_probability - float(row.outcome)) ** 2 for row in rows) / len(rows)
    candidate_log = sum(_binary_log_loss(row.candidate_probability, row.outcome) for row in rows) / len(rows)
    baseline_log = sum(_binary_log_loss(row.baseline_probability, row.outcome) for row in rows) / len(rows)

    rng = Random(random_seed)
    brier_deltas: list[float] = []
    log_deltas: list[float] = []
    for _ in range(bootstrap_iterations):
        sampled_rows: list[PairedPrediction] = []
        for _ in block_ids:
            sampled_block = rng.choice(block_ids)
            sampled_rows.extend(blocks[sampled_block])
        brier_delta, log_delta = _metric_deltas(sampled_rows)
        brier_deltas.append(brier_delta)
        log_deltas.append(log_delta)

    brier_deltas.sort()
    log_deltas.sort()
    alpha = (1 - confidence_level) / 2
    return PairedModelComparison(
        sample_size=len(rows),
        block_count=len(block_ids),
        candidate_brier=candidate_brier,
        baseline_brier=baseline_brier,
        brier_delta=candidate_brier - baseline_brier,
        brier_delta_ci_low=_quantile(brier_deltas, alpha),
        brier_delta_ci_high=_quantile(brier_deltas, 1 - alpha),
        candidate_log_loss=candidate_log,
        baseline_log_loss=baseline_log,
        log_loss_delta=candidate_log - baseline_log,
        log_loss_delta_ci_low=_quantile(log_deltas, alpha),
        log_loss_delta_ci_high=_quantile(log_deltas, 1 - alpha),
    )
