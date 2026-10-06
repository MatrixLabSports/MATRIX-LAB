"""Governed read-only adapters for additive free sports-data sources.

These adapters perform retrieval only. They do not generate probabilities,
place wagers, impute missing values, or override canonical paid-source data.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SourceResponse:
    source: str
    retrieved_at_utc: str
    payload: Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    req = Request(url, headers=headers or {"User-Agent": "MATRIX-LAB-SPORTS/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def football_data_matches(date_from: str, date_to: str) -> SourceResponse:
    token = os.getenv("FOOTBALL_DATA_ORG_TOKEN", "").strip()
    if not token:
        raise RuntimeError("FOOTBALL_DATA_ORG_TOKEN_MISSING")
    query = urlencode({"dateFrom": date_from, "dateTo": date_to})
    payload = _get_json(
        f"https://api.football-data.org/v4/matches?{query}",
        headers={"X-Auth-Token": token, "User-Agent": "MATRIX-LAB-SPORTS/1.0"},
    )
    return SourceResponse("football-data.org", _utc_now(), payload)


def thesportsdb_leagues(country: str, sport: str) -> SourceResponse:
    # Provider documents 123 as its public V1 free/development key.
    query = urlencode({"c": country, "s": sport})
    payload = _get_json(
        f"https://www.thesportsdb.com/api/v1/json/123/search_all_leagues.php?{query}"
    )
    return SourceResponse("TheSportsDB-v1-free", _utc_now(), payload)


def live_tennis_fixtures(tour: str | None = None, draw: str | None = None) -> SourceResponse:
    key = os.getenv("LIVE_TENNIS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("LIVE_TENNIS_API_KEY_MISSING")
    params: dict[str, str] = {}
    if tour:
        params["tour"] = tour
    if draw:
        params["draw"] = draw
    suffix = f"?{urlencode(params)}" if params else ""
    payload = _get_json(
        f"https://api.livetennisapi.com/api/public/v1/fixtures{suffix}",
        headers={"X-API-Key": key, "User-Agent": "MATRIX-LAB-SPORTS/1.0"},
    )
    return SourceResponse("Live-Tennis-API-free", _utc_now(), payload)


def activation_state() -> dict[str, str]:
    """Report configuration only; never equate key presence with a successful probe."""
    return {
        "football-data.org": "CONFIGURED_NOT_VERIFIED" if os.getenv("FOOTBALL_DATA_ORG_TOKEN") else "KEY_MISSING",
        "TheSportsDB-v1-free": "PUBLIC_FREE_KEY_AVAILABLE",
        "Live-Tennis-API-free": "CONFIGURED_NOT_VERIFIED" if os.getenv("LIVE_TENNIS_API_KEY") else "KEY_MISSING",
    }
