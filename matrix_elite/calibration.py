from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_probability: float | None
    observed_rate: float | None
    wilson_low: float | None
    wilson_high: float | None
    underpowered: bool


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n < 1:
        raise ValueError("WILSON_N_REQUIRED")
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def calibration_table(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    bins: int = 10,
    minimum_bin_n: int = 20,
) -> tuple[CalibrationBin, ...]:
    if bins < 2 or minimum_bin_n < 1:
        raise ValueError("CALIBRATION_CONFIGURATION_INVALID")
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("CALIBRATION_LENGTH_MISMATCH_OR_EMPTY")
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(probabilities, outcomes):
        p = float(p); y = int(y)
        if not 0 <= p <= 1:
            raise ValueError("PROBABILITY_OUT_OF_RANGE")
        if y not in (0, 1):
            raise ValueError("BINARY_OUTCOME_REQUIRED")
        idx = min(int(p * bins), bins - 1)
        buckets[idx].append((p, y))
    out: list[CalibrationBin] = []
    for i, bucket in enumerate(buckets):
        lo = i / bins; hi = (i + 1) / bins
        if not bucket:
            out.append(CalibrationBin(lo, hi, 0, None, None, None, None, True))
            continue
        n = len(bucket); successes = sum(y for _, y in bucket)
        wlo, whi = _wilson(successes, n)
        out.append(CalibrationBin(
            lo, hi, n,
            sum(p for p, _ in bucket) / n,
            successes / n,
            wlo, whi,
            n < minimum_bin_n,
        ))
    return tuple(out)


def maximum_calibration_gap(table: Sequence[CalibrationBin], *, include_underpowered: bool = False) -> float:
    gaps = []
    for b in table:
        if b.n == 0 or b.mean_probability is None or b.observed_rate is None:
            continue
        if b.underpowered and not include_underpowered:
            continue
        gaps.append(abs(b.mean_probability - b.observed_rate))
    if not gaps:
        raise ValueError("NO_POWERED_CALIBRATION_BINS")
    return max(gaps)
