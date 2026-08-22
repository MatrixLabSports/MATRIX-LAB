from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.providers.api_football.response_validation import (
    validate_api_football_response_envelope,
)


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _fixture_id(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValueError("INVALID_API_FOOTBALL_FIXTURE_ID")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            "INVALID_API_FOOTBALL_FIXTURE_ID"
        ) from error
    if parsed <= 0:
        raise ValueError("INVALID_API_FOOTBALL_FIXTURE_ID")
    return parsed


def _validated_items(
    client: Any,
    *,
    endpoint: str,
    params: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], ...], str]:
    # The caller must provide the already-governed API-Football client.
    # This module never creates a socket/session/transport and never
    # resolves a secret.
    payload = client.get(
        endpoint,
        params=dict(params),
    )
    envelope = validate_api_football_response_envelope(
        payload,
        endpoint=endpoint,
    )

    items: list[Mapping[str, Any]] = []
    for item in envelope.response:
        if not isinstance(item, Mapping):
            raise ValueError(
                "API_FOOTBALL_RESPONSE_ITEM_NOT_MAPPING"
            )
        items.append(dict(item))

    return tuple(items), envelope.payload_fingerprint


@dataclass(frozen=True)
class ApiFootballLiveBundle:
    fixture_id: int
    captured_at: datetime
    fixture: Mapping[str, Any]
    statistics: tuple[Mapping[str, Any], ...]
    events: tuple[Mapping[str, Any], ...]
    live_odds: tuple[Mapping[str, Any], ...]
    payload_fingerprints: Mapping[str, str]
    live_odds_requested: bool
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "captured_at",
            _aware_utc(
                self.captured_at,
                name="captured_at",
            ),
        )
        if self.fixture_id <= 0:
            raise ValueError(
                "INVALID_API_FOOTBALL_FIXTURE_ID"
            )
        if self.automatic_wagering is not False:
            raise ValueError(
                "AUTOMATIC_WAGERING_FORBIDDEN"
            )


def fetch_api_football_live_bundle(
    *,
    client: Any,
    fixture_id: int | str,
    include_live_odds: bool = True,
    clock: Callable[[], datetime] = (
        lambda: datetime.now(timezone.utc)
    ),
) -> ApiFootballLiveBundle:
    fid = _fixture_id(fixture_id)

    fixtures, fixture_fp = _validated_items(
        client,
        endpoint="/fixtures",
        params={"id": fid},
    )
    if len(fixtures) != 1:
        raise ValueError(
            "API_FOOTBALL_LIVE_FIXTURE_NOT_UNIQUE"
        )

    statistics, statistics_fp = _validated_items(
        client,
        endpoint="/fixtures/statistics",
        params={"fixture": fid},
    )
    events, events_fp = _validated_items(
        client,
        endpoint="/fixtures/events",
        params={"fixture": fid},
    )

    live_odds: tuple[Mapping[str, Any], ...] = ()
    fingerprints = {
        "fixture": fixture_fp,
        "statistics": statistics_fp,
        "events": events_fp,
    }

    if include_live_odds:
        live_odds, live_odds_fp = _validated_items(
            client,
            endpoint="/odds/live",
            params={"fixture": fid},
        )
        fingerprints["live_odds"] = live_odds_fp

    return ApiFootballLiveBundle(
        fixture_id=fid,
        captured_at=_aware_utc(
            clock(),
            name="clock",
        ),
        fixture=fixtures[0],
        statistics=statistics,
        events=events,
        live_odds=live_odds,
        payload_fingerprints=fingerprints,
        live_odds_requested=bool(include_live_odds),
    )
