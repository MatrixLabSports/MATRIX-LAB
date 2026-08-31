from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class Position:
    sport: str
    event_id: str
    market_id: str
    stake_fraction: float
    correlation_group: str


def fractional_kelly(decimal_odds: float, probability: float, fraction: float=0.25) -> float:
    b=float(decimal_odds)-1.0; p=float(probability); q=1-p
    if b <= 0 or not 0 <= p <= 1 or not 0 < fraction <= 1: raise ValueError("INVALID_KELLY_INPUT")
    raw=(b*p-q)/b
    return max(0.0, raw*fraction)

def exposure_audit(positions: Sequence[Position], *, max_event: float, max_day: float, max_group: float) -> dict:
    if any(p.stake_fraction < 0 for p in positions): raise ValueError("NEGATIVE_STAKE")
    event={}; group={}
    total=0.0
    for p in positions:
        total += p.stake_fraction
        event[p.event_id]=event.get(p.event_id,0)+p.stake_fraction
        group[p.correlation_group]=group.get(p.correlation_group,0)+p.stake_fraction
    return {
        "total_exposure": total,
        "event_cap_breached": any(v>max_event for v in event.values()),
        "daily_cap_breached": total>max_day,
        "correlation_cap_breached": any(v>max_group for v in group.values()),
    }

def deterministic_bankroll_stress(start_bankroll: float, loss_fractions: Sequence[float]) -> dict:
    if start_bankroll <= 0: raise ValueError("BANKROLL_INVALID")
    bankroll=float(start_bankroll); peak=bankroll; max_dd=0.0
    for loss in loss_fractions:
        if not 0 <= loss < 1: raise ValueError("LOSS_FRACTION_INVALID")
        bankroll *= (1-loss)
        peak=max(peak,bankroll)
        max_dd=max(max_dd,(peak-bankroll)/peak)
    return {"ending_bankroll": bankroll, "max_drawdown": max_dd}
