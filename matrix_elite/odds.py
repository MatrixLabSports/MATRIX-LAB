from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence
from .metrics import devig_multiplicative

@dataclass(frozen=True)
class OddsSnapshot:
    event_id: str
    market_id: str
    selection_id: str
    provider: str
    captured_at: datetime
    decimal_odds: float
    is_live: bool

    def __post_init__(self):
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None: raise ValueError("ODDS_TIMESTAMP_MUST_BE_AWARE")
        if self.decimal_odds <= 1: raise ValueError("ODDS_INVALID")
        if not all((self.event_id,self.market_id,self.selection_id,self.provider)): raise ValueError("ODDS_BINDING_KEY_REQUIRED")


def reject_stale(snapshot: OddsSnapshot, *, now: datetime, max_age: timedelta) -> None:
    if now.tzinfo is None or now.utcoffset() is None: raise ValueError("NOW_MUST_BE_AWARE")
    age=now-snapshot.captured_at
    if age.total_seconds()<0: raise ValueError("ODDS_FROM_FUTURE")
    if age>max_age: raise ValueError("STALE_ODDS_REJECTED")


def fair_market_probabilities(snapshots: Sequence[OddsSnapshot]) -> dict[str,float]:
    if len(snapshots)<2: raise ValueError("COMPLETE_MARKET_REQUIRED")
    key={(s.event_id,s.market_id,s.captured_at,s.provider,s.is_live) for s in snapshots}
    if len(key)!=1: raise ValueError("MARKET_SNAPSHOT_BINDING_MISMATCH")
    if len({s.selection_id for s in snapshots})!=len(snapshots): raise ValueError("DUPLICATE_SELECTION")
    probs=devig_multiplicative([s.decimal_odds for s in snapshots])
    return {s.selection_id:p for s,p in zip(snapshots,probs)}


def closing_line_value(*, taken_decimal_odds: float, closing_fair_probability: float) -> float:
    if taken_decimal_odds<=1 or not 0<=closing_fair_probability<=1: raise ValueError("CLV_INPUT_INVALID")
    return closing_fair_probability - 1/taken_decimal_odds
