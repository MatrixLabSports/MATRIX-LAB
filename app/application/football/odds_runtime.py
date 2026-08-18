from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.research.football.odds_ledger import FootballOddsQuote


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class FootballOddsSourcePolicy:
    authorized_providers: frozenset[str] = frozenset({"api_football", "the_odds_api"})
    max_prematch_capture_delay_seconds: int = 120
    max_live_capture_delay_seconds: int = 15
    max_closing_distance_seconds: int = 600
    min_decimal_odds: float = 1.01
    max_decimal_odds: float = 100.0

    def __post_init__(self) -> None:
        if not isinstance(self.authorized_providers, frozenset):
            raise TypeError("authorized_providers must be frozenset")
        if not self.authorized_providers:
            raise ValueError("authorized_providers cannot be empty")
        if self.max_prematch_capture_delay_seconds <= 0:
            raise ValueError("max_prematch_capture_delay_seconds must be > 0")
        if self.max_live_capture_delay_seconds <= 0:
            raise ValueError("max_live_capture_delay_seconds must be > 0")
        if self.max_closing_distance_seconds <= 0:
            raise ValueError("max_closing_distance_seconds must be > 0")
        if not 1.0 < self.min_decimal_odds <= self.max_decimal_odds:
            raise ValueError("invalid governed odds range")


@dataclass(frozen=True)
class FootballOddsGateDecision:
    accepted: bool
    blocked_reasons: tuple[str, ...]


def assess_odds_quote(
    quote: FootballOddsQuote,
    *,
    policy: FootballOddsSourcePolicy = FootballOddsSourcePolicy(),
) -> FootballOddsGateDecision:
    reasons: list[str] = []
    if quote.provider not in policy.authorized_providers:
        reasons.append("odds_provider_not_authorized")
    if not policy.min_decimal_odds <= quote.decimal_odds <= policy.max_decimal_odds:
        reasons.append("odds_outside_governed_range")
    delay = (quote.captured_at - quote.quoted_at).total_seconds()
    limit = (
        policy.max_live_capture_delay_seconds
        if quote.phase == "LIVE"
        else policy.max_prematch_capture_delay_seconds
    )
    if delay > limit:
        reasons.append("odds_capture_delay_exceeded")
    return FootballOddsGateDecision(
        accepted=not reasons,
        blocked_reasons=tuple(reasons),
    )


def select_closing_reference_quote(
    quotes: Iterable[FootballOddsQuote],
    *,
    fixture_id: str,
    market_key: str,
    selection_key: str,
    kickoff_at: datetime,
    policy: FootballOddsSourcePolicy = FootballOddsSourcePolicy(),
) -> FootballOddsQuote | None:
    kickoff = _utc(kickoff_at, name="kickoff_at")
    candidates: list[FootballOddsQuote] = []
    for quote in quotes:
        if quote.quote_role != "REFERENCE" or quote.phase != "PREMATCH":
            continue
        if quote.fixture_id != fixture_id:
            continue
        if quote.market_key != market_key or quote.selection_key != selection_key:
            continue
        if quote.quoted_at > kickoff:
            continue
        if (kickoff - quote.quoted_at).total_seconds() > policy.max_closing_distance_seconds:
            continue
        if not assess_odds_quote(quote, policy=policy).accepted:
            continue
        candidates.append(quote)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.quoted_at)


def decimal_clv(entry_odds: float, closing_odds: float) -> float:
    if entry_odds <= 1.0 or closing_odds <= 1.0:
        raise ValueError("decimal odds must be > 1")
    return entry_odds / closing_odds - 1.0
