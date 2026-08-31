from __future__ import annotations
from math import log
from typing import Sequence

_EPS=1e-15

def _prob(p: float) -> float:
    p=float(p)
    if not 0.0 <= p <= 1.0:
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    return min(max(p,_EPS),1-_EPS)

def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("LENGTH_MISMATCH_OR_EMPTY")
    return sum((_prob(p)-int(y))**2 for p,y in zip(probabilities,outcomes))/len(probabilities)

def log_loss(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("LENGTH_MISMATCH_OR_EMPTY")
    total=0.0
    for p,y in zip(probabilities,outcomes):
        p=_prob(p); y=int(y)
        if y not in (0,1): raise ValueError("BINARY_OUTCOME_REQUIRED")
        total += -(y*log(p)+(1-y)*log(1-p))
    return total/len(probabilities)

def expected_calibration_error(probabilities: Sequence[float], outcomes: Sequence[int], bins: int=10) -> float:
    if bins < 2: raise ValueError("BINS_TOO_SMALL")
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("LENGTH_MISMATCH_OR_EMPTY")
    buckets=[[] for _ in range(bins)]
    for p,y in zip(probabilities,outcomes):
        p=float(p)
        if not 0 <= p <= 1: raise ValueError("PROBABILITY_OUT_OF_RANGE")
        idx=min(int(p*bins),bins-1)
        buckets[idx].append((p,int(y)))
    n=len(probabilities); ece=0.0
    for b in buckets:
        if not b: continue
        conf=sum(x[0] for x in b)/len(b)
        acc=sum(x[1] for x in b)/len(b)
        ece += len(b)/n*abs(conf-acc)
    return ece

def devig_multiplicative(decimal_odds: Sequence[float]) -> tuple[float,...]:
    if len(decimal_odds)<2: raise ValueError("AT_LEAST_TWO_OUTCOMES_REQUIRED")
    implied=[]
    for odd in decimal_odds:
        odd=float(odd)
        if odd <= 1.0: raise ValueError("DECIMAL_ODDS_MUST_EXCEED_ONE")
        implied.append(1.0/odd)
    z=sum(implied)
    if z <= 0: raise ValueError("INVALID_OVERROUND")
    return tuple(x/z for x in implied)

def expected_value(decimal_odds: float, probability: float) -> float:
    odd=float(decimal_odds); p=float(probability)
    if odd <= 1.0 or not 0 <= p <= 1: raise ValueError("INVALID_PRICE_OR_PROBABILITY")
    return p*odd-1.0

def clv_probability(model_taken_odds: float, closing_fair_probability: float) -> float:
    """Probability-space CLV: closing fair probability minus taken implied probability.

    Positive means the closing market ultimately assigned more probability to the
    selected outcome than the price taken implied.
    """
    odd=float(model_taken_odds)
    if odd <= 1.0 or not 0 <= closing_fair_probability <= 1:
        raise ValueError("INVALID_CLV_INPUT")
    return float(closing_fair_probability) - 1.0/odd
