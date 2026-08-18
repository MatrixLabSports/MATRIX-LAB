from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable


def _utc(value: str, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _probability(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("model_probability must be numeric")
    number = float(value)
    if not isfinite(number) or not 0 <= number <= 1:
        raise ValueError("model_probability must be between 0 and 1")
    return number


def _odds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("decimal_odds must be numeric")
    number = float(value)
    if not isfinite(number) or number <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    return number


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class OddsSnapshot:
    fixture_id: str
    market_key: str
    selection_key: str
    source_provider: str
    source_reference: str
    observed_at_utc: str
    fixture_kickoff_utc: str
    decimal_odds: float
    source_authorized: bool
    phase: str = "PRE_MATCH"

    def __post_init__(self) -> None:
        for name in ("fixture_id", "market_key", "selection_key", "source_provider", "source_reference"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.source_authorized, bool):
            raise ValueError("source_authorized must be bool")
        phase = _text("phase", self.phase).upper()
        if phase != "PRE_MATCH":
            raise ValueError("paper-trading foundation currently accepts PRE_MATCH odds only")
        object.__setattr__(self, "phase", phase)
        observed = _utc(self.observed_at_utc, name="observed_at_utc")
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        if observed >= kickoff:
            raise ValueError("PRE_MATCH odds must be observed strictly before kickoff")
        object.__setattr__(self, "observed_at_utc", observed.isoformat())
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))

    @property
    def implied_probability(self) -> float:
        return 1.0 / self.decimal_odds

    def canonical_sha256(self) -> str:
        return _canonical_sha256(asdict(self))


@dataclass(frozen=True)
class PaperTradeObservation:
    decision_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    model_version: str
    model_probability: float
    decision_at_utc: str
    odds_snapshot_sha256: str
    decimal_odds: float
    outcome: bool | None = None
    settled_at_utc: str | None = None

    def __post_init__(self) -> None:
        for name in ("decision_id", "fixture_id", "market_key", "selection_key", "model_version"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "model_probability", _probability(self.model_probability))
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))
        decision_at = _utc(self.decision_at_utc, name="decision_at_utc")
        object.__setattr__(self, "decision_at_utc", decision_at.isoformat())

        digest = _text("odds_snapshot_sha256", self.odds_snapshot_sha256).lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("odds_snapshot_sha256 must be a valid SHA-256 digest")
        object.__setattr__(self, "odds_snapshot_sha256", digest)

        if self.outcome is not None and not isinstance(self.outcome, bool):
            raise ValueError("outcome must be bool or null")
        if self.outcome is None and self.settled_at_utc is not None:
            raise ValueError("unsettled paper trade cannot have settled_at_utc")
        if self.outcome is not None:
            if self.settled_at_utc is None:
                raise ValueError("settled paper trade requires settled_at_utc")
            settled_at = _utc(self.settled_at_utc, name="settled_at_utc")
            if settled_at < decision_at:
                raise ValueError("settled_at_utc cannot be before decision_at_utc")
            object.__setattr__(self, "settled_at_utc", settled_at.isoformat())

    @property
    def theoretical_edge(self) -> float:
        return self.model_probability * self.decimal_odds - 1.0

    @property
    def realized_unit_return(self) -> float | None:
        if self.outcome is None:
            return None
        return self.decimal_odds - 1.0 if self.outcome else -1.0

    def canonical_sha256(self) -> str:
        return _canonical_sha256(asdict(self))


@dataclass(frozen=True)
class PaperTradingSummary:
    market_key: str
    model_version: str
    observation_count: int
    settled_count: int
    positive_edge_count: int
    mean_theoretical_edge: float
    realized_units: float
    mean_realized_unit_return: float | None
    max_drawdown_units: float


def summarize_paper_trading(observations: Iterable[PaperTradeObservation]) -> PaperTradingSummary:
    rows = list(observations)
    if not rows:
        raise ValueError("paper trading summary requires observations")
    markets = {row.market_key for row in rows}
    versions = {row.model_version for row in rows}
    if len(markets) != 1 or len(versions) != 1:
        raise ValueError("paper trading summary must contain one market and model_version")
    decision_ids = [row.decision_id for row in rows]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("paper trading observations contain duplicate decision_id")
    fixture_keys = [(row.fixture_id, row.market_key, row.selection_key) for row in rows]
    if len(fixture_keys) != len(set(fixture_keys)):
        raise ValueError("only one paper decision per fixture/market/selection is allowed")

    settled_returns = [row.realized_unit_return for row in rows if row.realized_unit_return is not None]
    realized = float(sum(settled_returns)) if settled_returns else 0.0
    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in settled_returns:
        running += float(value)
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)

    return PaperTradingSummary(
        market_key=next(iter(markets)),
        model_version=next(iter(versions)),
        observation_count=len(rows),
        settled_count=len(settled_returns),
        positive_edge_count=sum(1 for row in rows if row.theoretical_edge > 0),
        mean_theoretical_edge=sum(row.theoretical_edge for row in rows) / len(rows),
        realized_units=realized,
        mean_realized_unit_return=(realized / len(settled_returns)) if settled_returns else None,
        max_drawdown_units=max_drawdown,
    )
