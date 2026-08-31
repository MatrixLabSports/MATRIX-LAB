from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Sequence

from .metrics import brier_score, log_loss


@dataclass(frozen=True)
class BlockBootstrapComparison:
    n: int
    block_length: int
    bootstrap_samples: int
    brier_improvement: float
    log_loss_improvement: float
    brier_ci95: tuple[float, float]
    log_loss_ci95: tuple[float, float]


def _percentile(values: list[float], q: float) -> float:
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(pos); hi = min(lo + 1, len(vals) - 1); frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _validate(model_p: Sequence[float], market_p: Sequence[float], outcomes: Sequence[int], block_length: int, bootstrap_samples: int) -> None:
    if not (len(model_p) == len(market_p) == len(outcomes)) or len(outcomes) < 20:
        raise ValueError("BLOCK_BOOTSTRAP_REQUIRES_EQUAL_LENGTH_AND_N_AT_LEAST_20")
    if type(block_length) is not int or block_length < 1 or block_length > len(outcomes):
        raise ValueError("BLOCK_LENGTH_INVALID")
    if type(bootstrap_samples) is not int or bootstrap_samples < 100:
        raise ValueError("BOOTSTRAP_SAMPLES_TOO_SMALL")


def paired_moving_block_bootstrap_model_vs_market(
    model_p: Sequence[float],
    market_p: Sequence[float],
    outcomes: Sequence[int],
    *,
    block_length: int,
    bootstrap_samples: int = 1000,
    seed: int = 836,
) -> BlockBootstrapComparison:
    """Paired moving-block bootstrap preserving local dependence and pairing."""
    _validate(model_p, market_p, outcomes, block_length, bootstrap_samples)
    n = len(outcomes)
    observed_brier = brier_score(market_p, outcomes) - brier_score(model_p, outcomes)
    observed_log = log_loss(market_p, outcomes) - log_loss(model_p, outcomes)
    starts = list(range(0, n - block_length + 1))
    rng = Random(seed)
    bd: list[float] = []
    ld: list[float] = []
    for _ in range(bootstrap_samples):
        indices: list[int] = []
        while len(indices) < n:
            start = starts[rng.randrange(len(starts))]
            indices.extend(range(start, start + block_length))
        indices = indices[:n]
        mp = [model_p[i] for i in indices]
        xp = [market_p[i] for i in indices]
        y = [outcomes[i] for i in indices]
        bd.append(brier_score(xp, y) - brier_score(mp, y))
        ld.append(log_loss(xp, y) - log_loss(mp, y))
    return BlockBootstrapComparison(
        n=n,
        block_length=block_length,
        bootstrap_samples=bootstrap_samples,
        brier_improvement=observed_brier,
        log_loss_improvement=observed_log,
        brier_ci95=(_percentile(bd, .025), _percentile(bd, .975)),
        log_loss_ci95=(_percentile(ld, .025), _percentile(ld, .975)),
    )
