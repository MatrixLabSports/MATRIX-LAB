from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable


def _validate_probability(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("probability debe ser numérica")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("probability debe estar entre 0 y 1")
    return value


@dataclass(frozen=True)
class BinaryPrediction:
    fixture_id: str
    market: str
    partition: str
    probability: float
    outcome: bool

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not self.market.strip():
            raise ValueError("fixture_id y market son obligatorios")
        if self.partition not in {"validation", "test"}:
            raise ValueError("evaluación de modelo solo admite validation/test")
        object.__setattr__(self, "probability", _validate_probability(self.probability))
        if not isinstance(self.outcome, bool):
            raise ValueError("outcome debe ser bool")


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_probability: float | None
    empirical_rate: float | None
    absolute_gap: float | None


@dataclass(frozen=True)
class BinaryModelEvaluation:
    market: str
    partition: str
    sample_size: int
    brier_score: float
    log_loss: float
    calibration_error: float
    positive_rate: float
    mean_probability: float
    bins: tuple[CalibrationBin, ...]


@dataclass(frozen=True)
class ModelPromotionPolicy:
    min_test_samples: int = 500
    max_brier_score: float = 0.22
    max_calibration_error: float = 0.05
    max_log_loss: float = 0.65

    def __post_init__(self) -> None:
        if self.min_test_samples <= 0:
            raise ValueError("min_test_samples debe ser positivo")
        for name in ("max_brier_score", "max_calibration_error", "max_log_loss"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} debe ser positivo")

    def reasons_not_promotable(self, evaluation: BinaryModelEvaluation) -> tuple[str, ...]:
        reasons: list[str] = []
        if evaluation.partition != "test":
            reasons.append("evaluation_not_test_partition")
        if evaluation.sample_size < self.min_test_samples:
            reasons.append("insufficient_test_sample")
        if evaluation.brier_score > self.max_brier_score:
            reasons.append("brier_above_limit")
        if evaluation.calibration_error > self.max_calibration_error:
            reasons.append("calibration_error_above_limit")
        if evaluation.log_loss > self.max_log_loss:
            reasons.append("log_loss_above_limit")
        return tuple(reasons)

    def is_promotable(self, evaluation: BinaryModelEvaluation) -> bool:
        return not self.reasons_not_promotable(evaluation)


def evaluate_binary_predictions(
    predictions: Iterable[BinaryPrediction],
    *,
    bin_count: int = 10,
) -> BinaryModelEvaluation:
    rows = list(predictions)
    if not rows:
        raise ValueError("se requiere al menos una predicción")
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or bin_count < 2:
        raise ValueError("bin_count debe ser entero >= 2")
    markets = {row.market for row in rows}
    partitions = {row.partition for row in rows}
    if len(markets) != 1 or len(partitions) != 1:
        raise ValueError("la evaluación debe contener un solo market y partition")
    fixture_ids = [row.fixture_id for row in rows]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("no se permiten múltiples predicciones del mismo fixture en una evaluación")

    y = [1.0 if row.outcome else 0.0 for row in rows]
    p = [row.probability for row in rows]
    brier = sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(rows)
    eps = 1e-15
    logloss = -sum(
        yi * log(min(max(pi, eps), 1 - eps))
        + (1 - yi) * log(min(max(1 - pi, eps), 1 - eps))
        for pi, yi in zip(p, y)
    ) / len(rows)

    bins: list[CalibrationBin] = []
    weighted_gap = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [row for row in rows if lower <= row.probability < upper or (index == bin_count - 1 and row.probability == 1.0)]
        if not members:
            bins.append(CalibrationBin(lower, upper, 0, None, None, None))
            continue
        mean_probability = sum(row.probability for row in members) / len(members)
        empirical_rate = sum(1.0 if row.outcome else 0.0 for row in members) / len(members)
        gap = abs(mean_probability - empirical_rate)
        weighted_gap += gap * len(members) / len(rows)
        bins.append(CalibrationBin(lower, upper, len(members), mean_probability, empirical_rate, gap))

    return BinaryModelEvaluation(
        market=next(iter(markets)),
        partition=next(iter(partitions)),
        sample_size=len(rows),
        brier_score=brier,
        log_loss=logloss,
        calibration_error=weighted_gap,
        positive_rate=sum(y) / len(rows),
        mean_probability=sum(p) / len(rows),
        bins=tuple(bins),
    )

_ALLOWED_1X2_CLASSES = ("H", "D", "A")


@dataclass(frozen=True)
class MulticlassPrediction:
    fixture_id: str
    market: str
    partition: str
    probabilities: dict[str, float]
    outcome: str

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not self.market.strip():
            raise ValueError("fixture_id y market son obligatorios")
        if self.partition not in {"validation", "test"}:
            raise ValueError("evaluación multiclass solo admite validation/test")
        if set(self.probabilities) != set(_ALLOWED_1X2_CLASSES):
            raise ValueError("1X2 probabilities must contain H/D/A exactly")
        normalized = {key: _validate_probability(value) for key, value in self.probabilities.items()}
        if abs(sum(normalized.values()) - 1.0) > 1e-9:
            raise ValueError("multiclass probabilities must sum to 1")
        if self.outcome not in _ALLOWED_1X2_CLASSES:
            raise ValueError("outcome must be H, D or A")
        object.__setattr__(self, "probabilities", normalized)


@dataclass(frozen=True)
class MulticlassModelEvaluation:
    market: str
    partition: str
    sample_size: int
    brier_score: float
    log_loss: float
    accuracy: float
    mean_confidence: float
    confidence_calibration_error: float
    class_rates: dict[str, float]


def evaluate_multiclass_predictions(
    predictions: Iterable[MulticlassPrediction],
    *,
    bin_count: int = 10,
) -> MulticlassModelEvaluation:
    rows = list(predictions)
    if not rows:
        raise ValueError("se requiere al menos una predicción multiclass")
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or bin_count < 2:
        raise ValueError("bin_count debe ser entero >= 2")
    markets = {row.market for row in rows}
    partitions = {row.partition for row in rows}
    if len(markets) != 1 or len(partitions) != 1:
        raise ValueError("la evaluación debe contener un solo market y partition")
    if len({row.fixture_id for row in rows}) != len(rows):
        raise ValueError("no se permiten múltiples predicciones del mismo fixture")

    brier_total = 0.0
    log_total = 0.0
    correct = 0
    confidences: list[tuple[float, bool]] = []
    class_counts = {key: 0 for key in _ALLOWED_1X2_CLASSES}
    eps = 1e-15

    for row in rows:
        class_counts[row.outcome] += 1
        for klass in _ALLOWED_1X2_CLASSES:
            target = 1.0 if row.outcome == klass else 0.0
            brier_total += (row.probabilities[klass] - target) ** 2
        actual_probability = min(max(row.probabilities[row.outcome], eps), 1.0)
        log_total += -log(actual_probability)
        predicted = max(_ALLOWED_1X2_CLASSES, key=lambda key: row.probabilities[key])
        is_correct = predicted == row.outcome
        correct += int(is_correct)
        confidences.append((row.probabilities[predicted], is_correct))

    weighted_gap = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [
            item for item in confidences
            if lower <= item[0] < upper or (index == bin_count - 1 and item[0] == 1.0)
        ]
        if not members:
            continue
        mean_confidence = sum(item[0] for item in members) / len(members)
        empirical_accuracy = sum(1.0 if item[1] else 0.0 for item in members) / len(members)
        weighted_gap += abs(mean_confidence - empirical_accuracy) * len(members) / len(rows)

    return MulticlassModelEvaluation(
        market=next(iter(markets)),
        partition=next(iter(partitions)),
        sample_size=len(rows),
        brier_score=brier_total / len(rows),
        log_loss=log_total / len(rows),
        accuracy=correct / len(rows),
        mean_confidence=sum(item[0] for item in confidences) / len(confidences),
        confidence_calibration_error=weighted_gap,
        class_rates={key: class_counts[key] / len(rows) for key in _ALLOWED_1X2_CLASSES},
    )
