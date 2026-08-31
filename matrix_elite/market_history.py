from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from statistics import mean
from typing import Iterable, Sequence

from .metrics import expected_value
from .odds import OddsSnapshot, fair_market_probabilities, reject_stale


@dataclass(frozen=True)
class BoundPriceDecision:
    event_id: str
    market_id: str
    selection_id: str
    provider: str
    captured_at: datetime
    decision_at: datetime
    decimal_odds: float
    fair_market_probability: float
    model_probability: float
    expected_value: float
    quote_sha256: str


@dataclass(frozen=True)
class ClosingLineEvidence:
    event_id: str
    market_id: str
    selection_id: str
    event_start_at: datetime
    provider_probabilities: tuple[tuple[str, float], ...]
    consensus_fair_probability: float
    latest_provider_capture_at: datetime
    providers_used: int


class MarketLineHistory:
    """Complete, hashable market snapshots keyed by canonical market identity."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str, str, bool, datetime], tuple[OddsSnapshot, ...]] = {}

    def add_complete_snapshot(self, snapshots: Sequence[OddsSnapshot], *, expected_selection_ids: Iterable[str]) -> str:
        expected = frozenset(expected_selection_ids)
        if len(expected) < 2:
            raise ValueError("EXPECTED_SELECTION_SET_INCOMPLETE")
        fair_market_probabilities(snapshots)  # validates common binding and odds
        actual = frozenset(s.selection_id for s in snapshots)
        if actual != expected:
            raise ValueError("MARKET_SELECTION_SET_MISMATCH")
        first = snapshots[0]
        key = (first.event_id, first.market_id, first.provider, first.is_live, first.captured_at)
        canonical = tuple(sorted(snapshots, key=lambda s: s.selection_id))
        prior = self._snapshots.get(key)
        if prior is not None and prior != canonical:
            raise ValueError("CONFLICTING_MARKET_SNAPSHOT_SAME_TIMESTAMP")
        self._snapshots[key] = canonical
        return market_snapshot_sha256(canonical)

    def _eligible_complete_snapshots(
        self,
        *,
        event_id: str,
        market_id: str,
        at_or_before: datetime,
        is_live: bool,
    ) -> tuple[tuple[OddsSnapshot, ...], ...]:
        _aware(at_or_before, "AT_OR_BEFORE")
        out = []
        for (e, m, _provider, live, captured), snapshot in self._snapshots.items():
            if e == event_id and m == market_id and live == is_live and captured <= at_or_before:
                out.append(snapshot)
        return tuple(out)

    def latest_by_provider(
        self,
        *,
        event_id: str,
        market_id: str,
        at_or_before: datetime,
        is_live: bool,
    ) -> dict[str, tuple[OddsSnapshot, ...]]:
        out: dict[str, tuple[OddsSnapshot, ...]] = {}
        for snapshot in self._eligible_complete_snapshots(event_id=event_id, market_id=market_id, at_or_before=at_or_before, is_live=is_live):
            provider = snapshot[0].provider
            prior = out.get(provider)
            if prior is None or snapshot[0].captured_at > prior[0].captured_at:
                out[provider] = snapshot
        return out

    def decision_state(
        self,
        *,
        event_id: str,
        market_id: str,
        selection_id: str,
        decision_at: datetime,
        model_probability: float,
        max_quote_age: timedelta,
        is_live: bool,
    ) -> BoundPriceDecision:
        _aware(decision_at, "DECISION_AT")
        latest = self.latest_by_provider(event_id=event_id, market_id=market_id, at_or_before=decision_at, is_live=is_live)
        candidates: list[tuple[OddsSnapshot, float]] = []
        for snapshot in latest.values():
            selection = next((s for s in snapshot if s.selection_id == selection_id), None)
            if selection is None:
                continue
            try:
                reject_stale(selection, now=decision_at, max_age=max_quote_age)
            except ValueError as exc:
                if str(exc) == "STALE_ODDS_REJECTED":
                    continue
                raise
            fair = fair_market_probabilities(snapshot)[selection_id]
            candidates.append((selection, fair))
        if not candidates:
            raise ValueError("NO_VALID_NONSTALE_PRICE")
        selected, fair_probability = max(candidates, key=lambda x: (x[0].decimal_odds, x[0].captured_at, x[0].provider))
        if not 0 <= model_probability <= 1:
            raise ValueError("MODEL_PROBABILITY_OUT_OF_RANGE")
        return BoundPriceDecision(
            event_id=event_id,
            market_id=market_id,
            selection_id=selection_id,
            provider=selected.provider,
            captured_at=selected.captured_at,
            decision_at=decision_at,
            decimal_odds=selected.decimal_odds,
            fair_market_probability=fair_probability,
            model_probability=float(model_probability),
            expected_value=expected_value(selected.decimal_odds, model_probability),
            quote_sha256=odds_snapshot_sha256(selected),
        )

    def prematch_closing_line(
        self,
        *,
        event_id: str,
        market_id: str,
        selection_id: str,
        event_start_at: datetime,
        max_close_age: timedelta,
    ) -> ClosingLineEvidence:
        _aware(event_start_at, "EVENT_START_AT")
        latest = self.latest_by_provider(event_id=event_id, market_id=market_id, at_or_before=event_start_at, is_live=False)
        provider_probs: list[tuple[str, float, datetime]] = []
        for provider, snapshot in latest.items():
            captured = snapshot[0].captured_at
            age = event_start_at - captured
            if age.total_seconds() < 0:
                raise ValueError("CLOSING_SNAPSHOT_FROM_FUTURE")
            if age > max_close_age:
                continue
            fair = fair_market_probabilities(snapshot)
            if selection_id in fair:
                provider_probs.append((provider, fair[selection_id], captured))
        if not provider_probs:
            raise ValueError("NO_VALID_PREMATCH_CLOSING_LINE")
        provider_probs.sort(key=lambda x: x[0])
        return ClosingLineEvidence(
            event_id=event_id,
            market_id=market_id,
            selection_id=selection_id,
            event_start_at=event_start_at,
            provider_probabilities=tuple((provider, probability) for provider, probability, _ in provider_probs),
            consensus_fair_probability=mean(probability for _, probability, _ in provider_probs),
            latest_provider_capture_at=max(captured for _, _, captured in provider_probs),
            providers_used=len(provider_probs),
        )


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_AWARE")
    return value


def odds_snapshot_sha256(snapshot: OddsSnapshot) -> str:
    row = {
        "event_id": snapshot.event_id,
        "market_id": snapshot.market_id,
        "selection_id": snapshot.selection_id,
        "provider": snapshot.provider,
        "captured_at": snapshot.captured_at.isoformat(),
        "decimal_odds": float(snapshot.decimal_odds),
        "is_live": bool(snapshot.is_live),
    }
    return sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def market_snapshot_sha256(snapshots: Sequence[OddsSnapshot]) -> str:
    if not snapshots:
        raise ValueError("EMPTY_MARKET_SNAPSHOT")
    # Validate and canonicalize so ordering cannot change the evidence hash.
    fair_market_probabilities(snapshots)
    rows = []
    for snapshot in sorted(snapshots, key=lambda s: s.selection_id):
        rows.append({
            "event_id": snapshot.event_id,
            "market_id": snapshot.market_id,
            "selection_id": snapshot.selection_id,
            "provider": snapshot.provider,
            "captured_at": snapshot.captured_at.isoformat(),
            "decimal_odds": float(snapshot.decimal_odds),
            "is_live": bool(snapshot.is_live),
        })
    return sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def probability_clv(*, taken_decimal_odds: float, closing: ClosingLineEvidence) -> float:
    if taken_decimal_odds <= 1:
        raise ValueError("TAKEN_ODDS_INVALID")
    return closing.consensus_fair_probability - (1.0 / taken_decimal_odds)


def fair_odds_clv_ratio(*, taken_decimal_odds: float, closing: ClosingLineEvidence) -> float:
    if taken_decimal_odds <= 1 or closing.consensus_fair_probability <= 0:
        raise ValueError("CLV_INPUT_INVALID")
    closing_fair_odds = 1.0 / closing.consensus_fair_probability
    return taken_decimal_odds / closing_fair_odds - 1.0
