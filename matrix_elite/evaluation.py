from __future__ import annotations
from dataclasses import dataclass
from random import Random
from typing import Sequence
from .metrics import brier_score, log_loss, expected_calibration_error

@dataclass(frozen=True)
class ModelComparison:
    n: int
    model_brier: float
    market_brier: float
    model_log_loss: float
    market_log_loss: float
    model_ece: float
    market_ece: float
    brier_improvement: float
    log_loss_improvement: float
    bootstrap_brier_improvement_ci95: tuple[float,float]
    bootstrap_log_loss_improvement_ci95: tuple[float,float]


def _percentile(values: list[float], q: float) -> float:
    vals=sorted(values)
    pos=(len(vals)-1)*q
    lo=int(pos); hi=min(lo+1,len(vals)-1); frac=pos-lo
    return vals[lo]*(1-frac)+vals[hi]*frac


def compare_model_to_market(model_p: Sequence[float], market_p: Sequence[float], outcomes: Sequence[int], *, bootstrap_samples: int=1000, seed: int=836) -> ModelComparison:
    if not (len(model_p)==len(market_p)==len(outcomes)) or len(outcomes)<20:
        raise ValueError("COMPARISON_REQUIRES_EQUAL_LENGTH_AND_N_AT_LEAST_20")
    mb=brier_score(model_p,outcomes); xb=brier_score(market_p,outcomes)
    ml=log_loss(model_p,outcomes); xl=log_loss(market_p,outcomes)
    me=expected_calibration_error(model_p,outcomes); xe=expected_calibration_error(market_p,outcomes)
    rng=Random(seed); n=len(outcomes); bd=[]; ld=[]
    for _ in range(bootstrap_samples):
        idx=[rng.randrange(n) for _ in range(n)]
        mp=[model_p[i] for i in idx]; xp=[market_p[i] for i in idx]; y=[outcomes[i] for i in idx]
        bd.append(brier_score(xp,y)-brier_score(mp,y))
        ld.append(log_loss(xp,y)-log_loss(mp,y))
    return ModelComparison(
        n=n, model_brier=mb, market_brier=xb, model_log_loss=ml, market_log_loss=xl,
        model_ece=me, market_ece=xe, brier_improvement=xb-mb, log_loss_improvement=xl-ml,
        bootstrap_brier_improvement_ci95=(_percentile(bd,.025),_percentile(bd,.975)),
        bootstrap_log_loss_improvement_ci95=(_percentile(ld,.025),_percentile(ld,.975)),
    )


def backtested_promotion_gate(comparison: ModelComparison, *, max_model_ece: float, require_ci_above_zero: bool=True) -> bool:
    if comparison.model_ece > max_model_ece: return False
    if comparison.brier_improvement <= 0 or comparison.log_loss_improvement <= 0: return False
    if require_ci_above_zero:
        return comparison.bootstrap_brier_improvement_ci95[0] > 0 and comparison.bootstrap_log_loss_improvement_ci95[0] > 0
    return True
