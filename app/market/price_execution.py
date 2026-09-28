from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable

from app.market.colombia_bookmakers import classify_bookmaker


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name}_MUST_BE_DATETIME")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_REQUIRED")
    return text


def _probability(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("P_MATRIX_MUST_BE_NUMERIC")
    p = float(value)
    if not 0.0 < p < 1.0:
        raise ValueError("P_MATRIX_OUT_OF_RANGE")
    return p


def _decimal_odds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("DECIMAL_ODDS_MUST_BE_NUMERIC")
    odds = float(value)
    if not isfinite(odds) or odds <= 1.0:
        raise ValueError("DECIMAL_ODDS_INVALID")
    return odds


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(payload: object) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelProbability:
    sport: str
    event_id: str
    market_key: str
    bet_type: str
    period: str
    selection_key: str
    side: str
    probability: float
    generated_at: datetime
    model_binding: str
    source_sha256: str
    metric: str | None = None
    line: str | float | int | None = None
    market_contract: str | None = None
    selection_parameters: str | None = None
    odds_used_as_input: bool = False

    def __post_init__(self) -> None:
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SPORT_INVALID")
        object.__setattr__(self, "event_id", _text(self.event_id, "EVENT_ID"))
        object.__setattr__(self, "market_key", _text(self.market_key, "MARKET_KEY"))
        object.__setattr__(self, "bet_type", _text(self.bet_type, "BET_TYPE"))
        object.__setattr__(self, "period", _text(self.period, "PERIOD"))
        object.__setattr__(self, "selection_key", _text(self.selection_key, "SELECTION_KEY"))
        object.__setattr__(self, "side", _text(self.side, "SIDE"))
        object.__setattr__(self, "probability", _probability(self.probability))
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "GENERATED_AT"))
        object.__setattr__(self, "model_binding", _text(self.model_binding, "MODEL_BINDING"))
        digest = _text(self.source_sha256, "SOURCE_SHA256").lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("SOURCE_SHA256_INVALID")
        object.__setattr__(self, "source_sha256", digest)
        if self.odds_used_as_input:
            raise ValueError("ODDS_TO_P_MATRIX_FORBIDDEN")

    @property
    def comparison_key(self) -> tuple[object, ...]:
        return (
            self.sport,
            self.event_id,
            self.market_key,
            self.bet_type,
            self.metric,
            self.period,
            self.line,
            self.side,
            self.selection_key,
            self.market_contract,
            self.selection_parameters,
        )


@dataclass(frozen=True)
class CanonicalOddsQuote:
    provider: str
    provider_event_id: str
    sport: str
    event_id: str
    bookmaker: str
    market_key: str
    bet_type: str
    period: str
    metric: str | None
    line: str | float | int | None
    side: str
    selection_key: str
    decimal_odds: float
    is_available: bool
    quoted_at: datetime
    captured_at: datetime
    event_start_at: datetime
    source_payload_sha256: str
    source_reference: str
    market_contract: str | None = None
    selection_parameters: str | None = None
    freshness_basis: str = "BOOKMAKER_AS_OF"

    def __post_init__(self) -> None:
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SPORT_INVALID")
        for name in (
            "provider", "provider_event_id", "event_id", "bookmaker", "market_key",
            "bet_type", "period", "side", "selection_key", "source_reference",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name.upper()))
        object.__setattr__(self, "bookmaker", self.bookmaker.casefold())
        object.__setattr__(self, "decimal_odds", _decimal_odds(self.decimal_odds))
        object.__setattr__(self, "quoted_at", _utc(self.quoted_at, "QUOTED_AT"))
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "CAPTURED_AT"))
        object.__setattr__(self, "event_start_at", _utc(self.event_start_at, "EVENT_START_AT"))
        if self.quoted_at > self.captured_at:
            raise ValueError("QUOTE_AFTER_CAPTURE")
        digest = _text(self.source_payload_sha256, "SOURCE_SHA256").lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("SOURCE_SHA256_INVALID")
        object.__setattr__(self, "source_payload_sha256", digest)

    @property
    def comparison_key(self) -> tuple[object, ...]:
        return (
            self.sport,
            self.event_id,
            self.market_key,
            self.bet_type,
            self.metric,
            self.period,
            self.line,
            self.side,
            self.selection_key,
            self.market_contract,
            self.selection_parameters,
        )

    @property
    def quote_fingerprint(self) -> str:
        return _sha({
            "provider": self.provider,
            "provider_event_id": self.provider_event_id,
            "bookmaker": self.bookmaker,
            "comparison_key": self.comparison_key,
            "decimal_odds": self.decimal_odds,
            "quoted_at": self.quoted_at.isoformat(),
            "source_payload_sha256": self.source_payload_sha256,
        })


@dataclass(frozen=True)
class QuoteGate:
    accepted: bool
    reasons: tuple[str, ...]
    age_seconds: float


@dataclass(frozen=True)
class BestPriceDecision:
    status: str
    quote: CanonicalOddsQuote | None
    model_probability: float
    implied_probability: float | None
    expected_value: float | None
    edge_probability_points: float | None
    compared_quotes: int
    accepted_quotes: int
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class StakePolicy:
    fractional_kelly: float = 0.25
    max_bankroll_fraction: float = 0.02
    min_bankroll_fraction: float = 0.0025
    min_expected_value: float = 0.0
    min_decimal_odds_exclusive: float = 1.50

    def __post_init__(self) -> None:
        if not 0 < self.fractional_kelly <= 1:
            raise ValueError("FRACTIONAL_KELLY_INVALID")
        if not 0 < self.min_bankroll_fraction <= self.max_bankroll_fraction <= 1:
            raise ValueError("BANKROLL_FRACTION_LIMITS_INVALID")
        if self.min_expected_value < 0:
            raise ValueError("MIN_EXPECTED_VALUE_INVALID")
        if self.min_decimal_odds_exclusive <= 1:
            raise ValueError("MIN_DECIMAL_ODDS_INVALID")


@dataclass(frozen=True)
class StakeDecision:
    status: str
    bankroll_fraction: float
    amount: float
    full_kelly_fraction: float
    fractional_kelly_fraction: float
    reasons: tuple[str, ...]


def assess_quote(
    quote: CanonicalOddsQuote,
    *,
    now: datetime,
    max_age_seconds: int = 180,
    require_execution_bookmaker: bool = True,
) -> QuoteGate:
    now_utc = _utc(now, "NOW")
    reasons: list[str] = []
    book = classify_bookmaker(quote.bookmaker)
    if require_execution_bookmaker and not book.execution_eligible:
        reasons.append("BOOKMAKER_NOT_EXECUTION_ELIGIBLE")
    if not quote.is_available:
        reasons.append("SELECTION_UNAVAILABLE")
    if quote.quoted_at >= quote.event_start_at or quote.captured_at >= quote.event_start_at:
        reasons.append("NOT_PREMATCH")
    age_seconds = (now_utc - quote.quoted_at).total_seconds()
    if age_seconds < 0:
        reasons.append("QUOTE_FROM_FUTURE")
    if age_seconds > max_age_seconds:
        reasons.append("QUOTE_STALE")
    return QuoteGate(not reasons, tuple(reasons), age_seconds)


def select_best_price(
    probability: ModelProbability,
    quotes: Iterable[CanonicalOddsQuote],
    *,
    now: datetime,
    max_age_seconds: int = 180,
    min_decimal_odds_exclusive: float = 1.50,
) -> BestPriceDecision:
    rows = list(quotes)
    if not rows:
        return BestPriceDecision(
            "NO_BET", None, probability.probability, None, None, None, 0, 0,
            ("NO_QUOTES",),
        )

    if any(row.sport != probability.sport or row.event_id != probability.event_id for row in rows):
        raise ValueError("PROBABILITY_QUOTE_EVENT_MISMATCH")

    matching = [row for row in rows if row.comparison_key == probability.comparison_key]
    if not matching:
        return BestPriceDecision(
            "NO_BET", None, probability.probability, None, None, None, len(rows), 0,
            ("NO_MARKET_SELECTION_MATCH",),
        )

    exact = matching

    accepted: list[CanonicalOddsQuote] = []
    rejected: list[str] = []
    now_utc = _utc(now, "NOW")
    for row in exact:
        gate = assess_quote(row, now=now_utc, max_age_seconds=max_age_seconds)
        if gate.accepted and row.decimal_odds > min_decimal_odds_exclusive:
            accepted.append(row)
        else:
            rejected.extend(gate.reasons)
            if row.decimal_odds <= min_decimal_odds_exclusive:
                rejected.append("ODDS_NOT_ABOVE_MINIMUM")

    if not accepted:
        return BestPriceDecision(
            "NO_BET", None, probability.probability, None, None, None,
            len(exact), 0, tuple(sorted(set(rejected))) or ("NO_ACCEPTED_QUOTES",),
        )

    best = max(accepted, key=lambda row: (row.decimal_odds, row.quoted_at))
    implied = 1.0 / best.decimal_odds
    ev = probability.probability * best.decimal_odds - 1.0
    edge_pp = (probability.probability - implied) * 100.0
    status = "PRICE_CANDIDATE" if ev > 0 else "NO_BET"
    reasons = () if ev > 0 else ("NON_POSITIVE_EXPECTED_VALUE",)
    return BestPriceDecision(
        status, best, probability.probability, implied, ev, edge_pp,
        len(exact), len(accepted), reasons,
    )


def calculate_stake(
    decision: BestPriceDecision,
    *,
    bankroll: float,
    calibration_gate_pass: bool,
    real_money_gate_open: bool,
    calibration_reliability: float = 1.0,
    risk_multiplier: float = 1.0,
    policy: StakePolicy = StakePolicy(),
) -> StakeDecision:
    if isinstance(bankroll, bool) or not isinstance(bankroll, (int, float)) or bankroll <= 0:
        raise ValueError("BANKROLL_INVALID")
    if isinstance(calibration_reliability, bool) or not isinstance(calibration_reliability, (int, float)) or not 0.0 <= float(calibration_reliability) <= 1.0:
        raise ValueError("CALIBRATION_RELIABILITY_INVALID")
    if isinstance(risk_multiplier, bool) or not isinstance(risk_multiplier, (int, float)) or not 0.0 <= float(risk_multiplier) <= 1.0:
        raise ValueError("RISK_MULTIPLIER_INVALID")
    reasons: list[str] = []
    if not calibration_gate_pass:
        reasons.append("CALIBRATION_GATE_NOT_PASS")
    if not real_money_gate_open:
        reasons.append("REAL_MONEY_BLOCKED")
    if decision.quote is None or decision.expected_value is None:
        reasons.append("NO_PRICE_CANDIDATE")
    elif decision.expected_value <= policy.min_expected_value:
        reasons.append("EXPECTED_VALUE_BELOW_THRESHOLD")
    if reasons:
        return StakeDecision("NO_BET", 0.0, 0.0, 0.0, 0.0, tuple(reasons))

    odds = decision.quote.decimal_odds
    p = decision.model_probability
    b = odds - 1.0
    q = 1.0 - p
    full_kelly = max(0.0, (b * p - q) / b)
    fractional = full_kelly * policy.fractional_kelly
    risk_adjusted = fractional * float(calibration_reliability) * float(risk_multiplier)
    capped = min(risk_adjusted, policy.max_bankroll_fraction)
    if capped < policy.min_bankroll_fraction:
        return StakeDecision(
            "NO_BET", 0.0, 0.0, full_kelly, fractional,
            ("STAKE_BELOW_MINIMUM",),
        )
    amount = float(bankroll) * capped
    return StakeDecision("BET_CANDIDATE", capped, amount, full_kelly, fractional, ())


def decision_fingerprint(
    probability: ModelProbability,
    price: BestPriceDecision,
    stake: StakeDecision,
) -> str:
    return _sha({
        "probability": {
            "sport": probability.sport,
            "event_id": probability.event_id,
            "market_key": probability.market_key,
            "bet_type": probability.bet_type,
            "metric": probability.metric,
            "period": probability.period,
            "line": probability.line,
            "side": probability.side,
            "selection_key": probability.selection_key,
            "market_contract": probability.market_contract,
            "selection_parameters": probability.selection_parameters,
            "probability": probability.probability,
            "generated_at": probability.generated_at.isoformat(),
            "model_binding": probability.model_binding,
            "source_sha256": probability.source_sha256,
            "odds_used_as_input": probability.odds_used_as_input,
        },
        "price": {
            "status": price.status,
            "quote_fingerprint": price.quote.quote_fingerprint if price.quote else None,
            "implied_probability": price.implied_probability,
            "expected_value": price.expected_value,
            "edge_probability_points": price.edge_probability_points,
            "compared_quotes": price.compared_quotes,
            "accepted_quotes": price.accepted_quotes,
            "rejection_reasons": price.rejection_reasons,
        },
        "stake": {
            "status": stake.status,
            "bankroll_fraction": stake.bankroll_fraction,
            "amount": stake.amount,
            "full_kelly_fraction": stake.full_kelly_fraction,
            "fractional_kelly_fraction": stake.fractional_kelly_fraction,
            "reasons": stake.reasons,
        },
    })
