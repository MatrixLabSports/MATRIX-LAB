from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    payload = client.get(endpoint, {"fixture": fixture_id})
    raw = payload.get("response", [])
    if not isinstance(raw, list):
        raise ValueError("respuesta de odds de API-Football inválida")
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
