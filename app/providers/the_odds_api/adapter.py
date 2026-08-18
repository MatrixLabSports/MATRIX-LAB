from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from app.research.football.odds_ledger import FootballOddsQuote


def _utc_iso(value: object, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _payload_sha256(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def adapt_the_odds_api_event(
    event: dict[str, Any],
    *,
    fixture_id: str,
    captured_at: datetime,
    market_keys: frozenset[str] = frozenset({"h2h", "totals", "spreads"}),
    quote_role: str = "REFERENCE",
    source_reference: str = "the_odds_api:/v4/sports/{sport}/odds",
) -> list[FootballOddsQuote]:
    if not isinstance(event, dict):
        raise TypeError("event must be dict")
    event_id = str(event.get("id", "")).strip()
    if not event_id:
        raise ValueError("event id is required")
    bookmakers = event.get("bookmakers", [])
    if not isinstance(bookmakers, list):
        raise ValueError("bookmakers must be list")
    quotes: list[FootballOddsQuote] = []
    digest = _payload_sha256(event)
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        bookmaker_key = str(bookmaker.get("key") or bookmaker.get("title") or "").strip()
        if not bookmaker_key:
            continue
        quoted_at = _utc_iso(bookmaker.get("last_update"), name="bookmaker.last_update")
        markets = bookmaker.get("markets", [])
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_key = str(market.get("key", "")).strip()
            if market_key not in market_keys:
                continue
            outcomes = market.get("outcomes", [])
            if not isinstance(outcomes, list):
                continue
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    continue
                selection = str(outcome.get("name", "")).strip()
                price = outcome.get("price")
                if not selection or isinstance(price, bool) or not isinstance(price, (int, float)):
                    continue
                quotes.append(
                    FootballOddsQuote(
                        provider="the_odds_api",
                        provider_event_id=event_id,
                        fixture_id=fixture_id,
                        bookmaker=bookmaker_key,
                        market_key=market_key,
                        selection_key=selection,
                        decimal_odds=float(price),
                        quoted_at=quoted_at,
                        captured_at=captured_at,
                        phase="PREMATCH",
                        quote_role=quote_role,
                        source_payload_sha256=digest,
                        source_reference=source_reference,
                    )
                )
    return quotes
