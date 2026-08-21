from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
    request_and_validate_api_football_response,
)


@dataclass(frozen=True)
class ApiFootballOddsIngestion:
    response: list[dict[str, Any]]
    received_count: int
    rejected_count: int
    endpoint: str


def get_fixture_odds_raw(
    client: Any,
    fixture_id: int | str,
    *,
    live: bool = False,
) -> ApiFootballOddsIngestion:
    endpoint = "/odds/live" if live else "/odds"
    try:
        envelope = request_and_validate_api_football_response(
            client,
            endpoint=endpoint,
            params={"fixture": fixture_id},
        )
    except ApiFootballProviderResponseError as error:
        if error.code == "API_FOOTBALL_RESPONSE_FIELD_INVALID":
            raise ValueError('respuesta de odds de API-Football inv\u00e1lida') from error
        raise
    raw = list(envelope.response)
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for item in raw:
        if isinstance(item, dict):
            accepted.append(item)
        else:
            rejected += 1
    return ApiFootballOddsIngestion(
        response=accepted,
        received_count=len(raw),
        rejected_count=rejected,
        endpoint=endpoint,
    )
