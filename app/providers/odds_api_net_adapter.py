from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

from app.market.price_execution import CanonicalOddsQuote


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _ts_ms(value: object, name: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}_REQUIRED")
    return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)


def _optional_contract(value: object) -> str | None:
    if value in (None, "", {}, []):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return _canonical_json(value)


def _selection_key(item: Mapping[str, Any]) -> tuple[str, str]:
    explicit = str(item.get("selection_key") or "").strip()
    if explicit:
        return explicit, "PROVIDER_SELECTION_KEY"
    # Compact responses may omit selection_key. This local identity is valid for
    # exact in-snapshot comparison only; it is not represented as a provider
    # history key.
    payload = {
        "market_key": item.get("market_key"),
        "bet_type": item.get("bet_type"),
        "metric": item.get("metric"),
        "period": item.get("period"),
        "line": item.get("line"),
        "side": item.get("side"),
        "selection_name": item.get("selection_name"),
    }
    if not str(item.get("side") or "").strip() and not str(item.get("selection_name") or "").strip():
        raise ValueError("SELECTION_IDENTITY_MISSING")
    return "matrix-local:" + _digest(payload), "DERIVED_LOCAL_EXACT_SNAPSHOT_ONLY"


def adapt_odds_api_net_snapshot(
    snapshot: Mapping[str, Any],
    *,
    sport: str,
    matrix_event_id: str,
    event_start_at: datetime,
    captured_at: datetime,
    source_reference: str = "odds-api.net:/v1/events/{event_id}/odds/snapshot",
) -> tuple[list[CanonicalOddsQuote], dict[str, Any]]:
    if not isinstance(snapshot, Mapping):
        raise TypeError("SNAPSHOT_MUST_BE_MAPPING")
    provider_event_id = str(snapshot.get("event_id") or "").strip()
    if not provider_event_id:
        raise ValueError("PROVIDER_EVENT_ID_REQUIRED")
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise ValueError("SNAPSHOT_ITEMS_MUST_BE_LIST")

    as_of = _ts_ms(snapshot.get("as_of_ts_ms"), "AS_OF_TS_MS")
    bookmaker_as_of = snapshot.get("bookmaker_as_of_ts_ms")
    bookmaker_as_of = bookmaker_as_of if isinstance(bookmaker_as_of, Mapping) else {}
    digest = _digest(snapshot)

    quotes: list[CanonicalOddsQuote] = []
    skipped: list[dict[str, str]] = []
    local_selection_keys = 0
    provider_selection_keys = 0

    for index, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            skipped.append({"index": str(index), "reason": "ITEM_NOT_MAPPING"})
            continue
        bookmaker = str(raw.get("bookmaker") or "").strip().casefold()
        market_key = str(raw.get("market_key") or "").strip()
        bet_type = str(raw.get("bet_type") or "").strip()
        period = str(raw.get("period") or "").strip()
        side = str(raw.get("side") or "").strip()
        odds = raw.get("odds")
        if not all((bookmaker, market_key, bet_type, period, side)):
            skipped.append({"index": str(index), "reason": "COMPARISON_FIELDS_MISSING"})
            continue
        if isinstance(odds, bool) or not isinstance(odds, (int, float)):
            skipped.append({"index": str(index), "reason": "ODDS_MISSING_OR_INVALID"})
            continue

        try:
            selection_key, selection_origin = _selection_key(raw)
        except ValueError:
            skipped.append({"index": str(index), "reason": "SELECTION_IDENTITY_MISSING"})
            continue
        if selection_origin == "PROVIDER_SELECTION_KEY":
            provider_selection_keys += 1
        else:
            local_selection_keys += 1

        book_ts = bookmaker_as_of.get(bookmaker)
        if isinstance(book_ts, (int, float)) and not isinstance(book_ts, bool):
            quoted_at = _ts_ms(book_ts, "BOOKMAKER_AS_OF_TS_MS")
            freshness_basis = "BOOKMAKER_AS_OF"
        else:
            quoted_at = as_of
            freshness_basis = "SNAPSHOT_AS_OF_FALLBACK"

        metric_raw = raw.get("metric")
        metric = str(metric_raw).strip() if metric_raw not in (None, "") else None

        quote = CanonicalOddsQuote(
            provider="odds_api_net",
            provider_event_id=provider_event_id,
            sport=sport,
            event_id=matrix_event_id,
            bookmaker=bookmaker,
            market_key=market_key,
            bet_type=bet_type,
            period=period,
            metric=metric,
            line=raw.get("line"),
            side=side,
            selection_key=selection_key,
            decimal_odds=float(odds),
            is_available=bool(raw.get("is_available", True)),
            quoted_at=quoted_at,
            captured_at=captured_at,
            event_start_at=event_start_at,
            source_payload_sha256=digest,
            source_reference=source_reference,
            market_contract=_optional_contract(raw.get("market_contract")),
            selection_parameters=_optional_contract(raw.get("selection_parameters")),
            freshness_basis=freshness_basis,
        )
        quotes.append(quote)

    metadata = {
        "schema": "MATRIX_ODDS_API_NET_SNAPSHOT_ADAPTER_V1",
        "provider_event_id": provider_event_id,
        "matrix_event_id": matrix_event_id,
        "sport": sport,
        "snapshot_as_of_utc": as_of.isoformat(),
        "snapshot_sha256": digest,
        "input_items": len(items),
        "adapted_quotes": len(quotes),
        "skipped_items": skipped,
        "provider_selection_keys": provider_selection_keys,
        "local_selection_keys": local_selection_keys,
        "local_selection_key_history_eligible": False,
        "resume": snapshot.get("resume"),
        "next_cursor": snapshot.get("next_cursor"),
        "complete": snapshot.get("complete"),
        "target_refresh_interval_seconds": snapshot.get("target_refresh_interval_seconds"),
        "ttl_seconds": snapshot.get("ttl_seconds"),
        "odds_used_to_generate_model_probability": False,
        "real_money": "BLOCKED",
    }
    return quotes, metadata
