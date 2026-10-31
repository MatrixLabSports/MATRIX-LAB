from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

from app.research.football.odds_ledger import FootballOddsQuote

PINNACLE_BOOKMAKER_ID = 4
PINNACLE_BOOKMAKER_NAME = "Pinnacle"

_MARKET_KEYS = {
    1: "match_winner",
    4: "asian_handicap",
    5: "total_goals",
    6: "first_half_total_goals",
    13: "first_half_winner",
    16: "home_team_total_goals",
    17: "away_team_total_goals",
    19: "first_half_asian_handicap",
    45: "total_corners",
    56: "corners_asian_handicap",
    77: "first_half_total_corners",
    105: "home_first_half_total_goals",
}


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def market_key(bet_id: object, bet_name: str) -> str:
    try:
        parsed = int(bet_id)
    except (TypeError, ValueError):
        parsed = -1
    if parsed in _MARKET_KEYS:
        return _MARKET_KEYS[parsed]
    suffix = _slug(str(bet_name or "")) or "unknown"
    return f"api_football_bet_{parsed}_{suffix}"


@dataclass(frozen=True)
class PinnacleReferenceParseResult:
    quotes: tuple[FootballOddsQuote, ...]
    rejected_values: int
    fixture_ids: tuple[str, ...]
    market_keys: tuple[str, ...]
    source_payload_sha256: str


def parse_pinnacle_reference_quotes(
    raw_body: bytes,
    *,
    captured_at: datetime,
    source_reference: str,
) -> PinnacleReferenceParseResult:
    if not isinstance(raw_body, (bytes, bytearray)):
        raise TypeError("raw_body must be bytes")
    captured = captured_at.astimezone(timezone.utc)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    payload = json.loads(bytes(raw_body).decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("API_FOOTBALL_ODDS_PAYLOAD_INVALID")
    errors = payload.get("errors")
    if errors not in ({}, [], None):
        raise ValueError("API_FOOTBALL_ODDS_PROVIDER_ERROR")
    rows = payload.get("response")
    if not isinstance(rows, list):
        raise ValueError("API_FOOTBALL_ODDS_RESPONSE_INVALID")

    digest = sha256(bytes(raw_body)).hexdigest()
    quotes: list[FootballOddsQuote] = []
    rejected = 0
    fixtures: set[str] = set()
    markets: set[str] = set()

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        fixture = row.get("fixture")
        fixture = fixture if isinstance(fixture, Mapping) else {}
        fixture_id = str(fixture.get("id") or "").strip()
        if not fixture_id:
            continue
        update = row.get("update")
        if not update:
            continue
        quoted_at = _aware(str(update))
        if quoted_at > captured:
            raise ValueError("PINNACLE_QUOTE_TIMESTAMP_AFTER_CAPTURE")

        bookmakers = row.get("bookmakers")
        if not isinstance(bookmakers, list):
            continue
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, Mapping):
                continue
            if str(bookmaker.get("id")) != str(PINNACLE_BOOKMAKER_ID):
                continue
            if str(bookmaker.get("name") or "").strip().casefold() != PINNACLE_BOOKMAKER_NAME.casefold():
                continue
            bets = bookmaker.get("bets")
            if not isinstance(bets, list):
                continue
            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                bet_name = str(bet.get("name") or "").strip()
                mkey = market_key(bet.get("id"), bet_name)
                values = bet.get("values")
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, Mapping):
                        continue
                    selection = str(value.get("value") or "").strip()
                    raw_odd = value.get("odd")
                    try:
                        odd = float(raw_odd)
                    except (TypeError, ValueError):
                        rejected += 1
                        continue
                    if not selection or odd <= 1.0:
                        rejected += 1
                        continue
                    quote = FootballOddsQuote(
                        provider="api_football",
                        provider_event_id=fixture_id,
                        fixture_id=fixture_id,
                        bookmaker="Pinnacle",
                        market_key=mkey,
                        selection_key=selection,
                        decimal_odds=odd,
                        quoted_at=quoted_at,
                        captured_at=captured,
                        phase="PREMATCH",
                        quote_role="REFERENCE",
                        source_payload_sha256=digest,
                        source_reference=(
                            f"{source_reference};fixture={fixture_id};bookmaker=4;"
                            f"bet={bet.get('id')};selection={selection}"
                        ),
                    )
                    quotes.append(quote)
                    fixtures.add(fixture_id)
                    markets.add(mkey)

    return PinnacleReferenceParseResult(
        quotes=tuple(quotes),
        rejected_values=rejected,
        fixture_ids=tuple(sorted(fixtures)),
        market_keys=tuple(sorted(markets)),
        source_payload_sha256=digest,
    )
