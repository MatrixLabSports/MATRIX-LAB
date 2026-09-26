from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, quote_plus
from urllib.request import Request, urlopen

from app.research.tennis.world_calendar_registry import (
    WorldCalendarEvent,
    build_world_calendar_registry,
)

API_URL = "https://api.api-tennis.com/tennis/"
CHALLENGER_MEN_SINGLES_KEY = "281"
CHALLENGER_MEN_SINGLES_NAME = "Challenger Men Singles"
MAX_RESPONSE_BYTES = 5_000_000
MAX_DRAW_REQUESTS = 12
TERMINAL_STATUSES = {
    "FINISHED", "CANCELLED", "CANCELED", "ABANDONED", "RETIRED", "WALKOVER", "WO",
}


class ApiTennisDiscoveryError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_error(value: object, secret: str) -> str:
    text = str(value)
    candidates = {secret, quote(secret, safe=""), quote_plus(secret, safe="")}
    for candidate in sorted((x for x in candidates if x), key=len, reverse=True):
        text = text.replace(candidate, "[REDACTED]")
    return text[:500]


def _read_bounded(response, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ApiTennisDiscoveryError("API_TENNIS_RESPONSE_TOO_LARGE")
    return body


class ApiTennisDiscoveryClient:
    def __init__(
        self,
        api_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("API_TENNIS_KEY_REQUIRED")
        self._api_key = api_key.strip()
        self._opener = opener
        self._timeout = float(timeout_seconds)
        self.request_count = 0

    def _post(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        public = {str(k): str(v) for k, v in params.items() if v is not None}
        form = {"method": method, **public, "APIkey": self._api_key}
        data = urlencode(form).encode("utf-8")
        request = Request(
            API_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "MATRIX-COR0203-DISCOVERY/1.0",
                "Accept": "application/json",
            },
            method="POST",
        )
        self.request_count += 1
        try:
            with self._opener(request, timeout=self._timeout) as response:
                body = _read_bounded(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ApiTennisDiscoveryError(
                "API_TENNIS_NETWORK_ERROR:" + _safe_error(error, self._api_key)
            ) from None

        secret_bytes = self._api_key.encode("utf-8")
        if secret_bytes and secret_bytes in body:
            raise ApiTennisDiscoveryError("API_TENNIS_SECRET_ECHO_DETECTED")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiTennisDiscoveryError("API_TENNIS_INVALID_JSON") from error
        if not isinstance(payload, Mapping):
            raise ApiTennisDiscoveryError("API_TENNIS_RESPONSE_NOT_MAPPING")
        if int(payload.get("success", 0) or 0) != 1:
            raise ApiTennisDiscoveryError("API_TENNIS_PROVIDER_FAILURE")
        return dict(payload)

    def fixtures(self, start: date, stop: date) -> Mapping[str, Any]:
        if stop < start:
            raise ValueError("INVALID_DISCOVERY_DATE_RANGE")
        if (stop - start).days > 3:
            raise ValueError("DISCOVERY_RANGE_EXCEEDS_4_DAYS")
        return self._post(
            "get_fixtures",
            {
                "date_start": start.isoformat(),
                "date_stop": stop.isoformat(),
                "event_type_key": CHALLENGER_MEN_SINGLES_KEY,
                "timezone": "UTC",
            },
        )

    def draw(self, tournament_key: str, tournament_season: str) -> Mapping[str, Any]:
        if not str(tournament_key).strip():
            raise ValueError("TOURNAMENT_KEY_REQUIRED")
        if not re.fullmatch(r"\d{4}", str(tournament_season)):
            raise ValueError("TOURNAMENT_SEASON_INVALID")
        return self._post(
            "get_draw",
            {
                "tournament_key": str(tournament_key),
                "tournament_season": str(tournament_season),
                "include_qualification": "1",
                "timezone": "UTC",
            },
        )


def _result_list(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list):
        raise ApiTennisDiscoveryError("API_TENNIS_FIXTURE_RESULT_NOT_LIST")
    rows: list[Mapping[str, Any]] = []
    for row in result:
        if isinstance(row, Mapping):
            rows.append(row)
    return rows


def _draw_surface(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return None, None
    tournament = result.get("tournament")
    if not isinstance(tournament, Mapping):
        return None, str(result.get("source") or "") or None
    surface = str(tournament.get("tournament_surface") or "").strip() or None
    source = str(result.get("source") or "").strip() or None
    return surface, source


def _parse_fixture_start(row: Mapping[str, Any]) -> datetime:
    day = str(row.get("event_date") or "").strip()
    clock = str(row.get("event_time") or "").strip()
    if not day or not clock:
        raise ValueError("FIXTURE_START_MISSING")
    parsed = datetime.fromisoformat(f"{day}T{clock}:00+00:00")
    return parsed.astimezone(timezone.utc)


def _real_player_key(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def _event_key(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def build_discovery_registry(
    *,
    fixture_payload: Mapping[str, Any],
    draw_payloads: Mapping[str, Mapping[str, Any]],
    as_of_utc: str,
) -> dict[str, Any]:
    as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    events: list[WorldCalendarEvent] = []
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in _result_list(fixture_payload):
        event_key = _event_key(row.get("event_key"))
        event_type = str(row.get("event_type_type") or "").strip()
        tournament_key = str(row.get("tournament_key") or "").strip()
        season = str(row.get("tournament_season") or "").strip()
        status = str(row.get("event_status") or "").strip().upper()
        p1_key = _real_player_key(row.get("first_player_key"))
        p2_key = _real_player_key(row.get("second_player_key"))
        blockers: list[str] = []

        if event_type != CHALLENGER_MEN_SINGLES_NAME:
            blockers.append("NOT_CHALLENGER_MEN_SINGLES")
        if event_key is None:
            blockers.append("EVENT_KEY_INVALID")
        if not tournament_key:
            blockers.append("TOURNAMENT_KEY_MISSING")
        if status in TERMINAL_STATUSES:
            blockers.append("TERMINAL_EVENT")
        if p1_key is None or p2_key is None or p1_key == p2_key:
            blockers.append("PLAYER_KEYS_NOT_FIXED")

        try:
            start = _parse_fixture_start(row)
            if start <= as_of:
                blockers.append("EVENT_NOT_FUTURE")
        except (TypeError, ValueError):
            start = None
            blockers.append("START_AUTHORITY_INVALID")

        draw_payload = draw_payloads.get(tournament_key)
        surface, draw_source = _draw_surface(draw_payload or {})
        if surface is None:
            blockers.append("DRAW_SURFACE_MISSING")
        elif surface.strip().upper() != "HARD":
            blockers.append("SURFACE_OUT_OF_DOMAIN")

        if blockers:
            rejected.append({
                "event_key": event_key,
                "tournament_key": tournament_key or None,
                "blockers": sorted(set(blockers)),
            })
            continue

        source_snapshot_sha = _sha({
            "fixture": row,
            "draw_tournament": (draw_payload or {}).get("result", {}).get("tournament")
            if isinstance((draw_payload or {}).get("result"), Mapping)
            else None,
            "draw_source": draw_source,
        })
        round_name = str(row.get("tournament_round") or "").strip() or "UNKNOWN_ROUND"
        tournament_name = str(row.get("tournament_name") or "").strip() or f"api-tennis:{tournament_key}"

        events.append(WorldCalendarEvent(
            event_id=f"api-tennis:event:{event_key}",
            sport="TENNIS",
            competition_id=f"api-tennis:tournament:{tournament_key}",
            competition_name=tournament_name,
            tour_level="ATP_CHALLENGER",
            surface="Hard",
            environment="UNKNOWN",
            round=round_name,
            event_start_utc=start.isoformat(),
            player1_id=f"api-tennis:player:{p1_key}",
            player2_id=f"api-tennis:player:{p2_key}",
            source_provider="api_tennis",
            source_reference=(
                f"get_fixtures:event_key={event_key};"
                f"get_draw:tournament_key={tournament_key};season={season};source={draw_source or 'UNKNOWN'}"
            ),
            source_snapshot_sha256=source_snapshot_sha,
        ))

        candidates.append({
            "event_id": f"api-tennis:event:{event_key}",
            "canonical_source_event_id": f"api-tennis:event:{event_key}",
            "competition_id": f"api-tennis:tournament:{tournament_key}",
            "competition": tournament_name,
            "round": round_name,
            "surface": "Hard",
            "tour_level": "C",
            "event_start_utc": start.isoformat(),
            "target_period": 20260921,
            "source_provider": "api_tennis",
            "source_reference": (
                f"get_fixtures:event_key={event_key};"
                f"get_draw:tournament_key={tournament_key};season={season};source={draw_source or 'UNKNOWN'}"
            ),
            "source_snapshot_sha256": source_snapshot_sha,
            "players": [
                {
                    "name": str(row.get("event_first_player") or "").strip(),
                    "provider_player_id": f"api-tennis:player:{p1_key}",
                },
                {
                    "name": str(row.get("event_second_player") or "").strip(),
                    "provider_player_id": f"api-tennis:player:{p2_key}",
                },
            ],
            "historical_identity_crosswalk_status": "PENDING",
        })

    registry = build_world_calendar_registry(events=events, as_of_utc=as_of_utc)
    return {
        "schema": "MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
        "provider": "api_tennis",
        "as_of_utc": as_of.isoformat(),
        "fixture_rows": len(_result_list(fixture_payload)),
        "eligible_input_events": len(events),
        "eligible_candidates": candidates,
        "provider_rejected": rejected,
        "world_registry": registry,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def fetch_discovery(
    *,
    client: ApiTennisDiscoveryClient,
    start: date,
    stop: date,
    as_of_utc: str,
) -> dict[str, Any]:
    fixtures = client.fixtures(start, stop)
    rows = _result_list(fixtures)
    tournaments: dict[str, str] = {}
    for row in rows:
        if str(row.get("event_type_type") or "").strip() != CHALLENGER_MEN_SINGLES_NAME:
            continue
        key = str(row.get("tournament_key") or "").strip()
        season = str(row.get("tournament_season") or "").strip()
        if key and re.fullmatch(r"\d{4}", season):
            tournaments[key] = season

    draw_payloads: dict[str, Mapping[str, Any]] = {}
    for key in sorted(tournaments)[:MAX_DRAW_REQUESTS]:
        draw_payloads[key] = client.draw(key, tournaments[key])

    result = build_discovery_registry(
        fixture_payload=fixtures,
        draw_payloads=draw_payloads,
        as_of_utc=as_of_utc,
    )
    result["request_count"] = client.request_count
    result["draw_requests"] = len(draw_payloads)
    result["draw_request_limit"] = MAX_DRAW_REQUESTS
    result["tournaments_seen"] = len(tournaments)
    if len(tournaments) > MAX_DRAW_REQUESTS:
        result["provider_rejected"].append({
            "event_key": None,
            "tournament_key": None,
            "blockers": ["DRAW_REQUEST_LIMIT_REACHED"],
            "unqueried_tournaments": len(tournaments) - MAX_DRAW_REQUESTS,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()

    out = Path(args.out)
    key = os.environ.get("API_TENNIS_KEY", "").strip()
    as_of = args.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    now = datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(timezone.utc)

    if not key:
        payload = {
            "schema": "MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
            "provider": "api_tennis",
            "as_of_utc": now.isoformat(),
            "status": "API_TENNIS_KEY_NOT_CONFIGURED",
            "network_calls": 0,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
    else:
        days = max(1, min(int(args.days), 4))
        client = ApiTennisDiscoveryClient(key)
        try:
            payload = fetch_discovery(
                client=client,
                start=now.date(),
                stop=now.date() + timedelta(days=days - 1),
                as_of_utc=now.isoformat(),
            )
            payload["status"] = "DISCOVERY_COMPLETED"
            payload["network_calls"] = client.request_count
        except ApiTennisDiscoveryError as error:
            payload = {
                "schema": "MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
                "provider": "api_tennis",
                "as_of_utc": now.isoformat(),
                "status": "PROVIDER_DISCOVERY_BLOCKED",
                "blocker": _safe_error(error, key),
                "network_calls": client.request_count,
                "automatic_model_promotion": False,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload.get("status"),
        "network_calls": payload.get("network_calls", 0),
        "eligible": payload.get("world_registry", {}).get("cor0203_eligible_events", 0),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
