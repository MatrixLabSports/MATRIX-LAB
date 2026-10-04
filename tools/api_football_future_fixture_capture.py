from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT = "/fixtures"
TIMEZONE_NAME = "America/Bogota"
TIMEOUT_SECONDS = 20.0
PUBLIC_HEADER_ALLOWLIST = (
    "content-type",
    "date",
    "x-ratelimit-requests-limit",
    "x-ratelimit-requests-remaining",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
)
FUTURE_STATUSES = {"NS", "TBD"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_aware_iso(value: object) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _event_projection(raw: Any, *, captured_at: datetime) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, dict):
        return None, "FIXTURE_NOT_OBJECT"
    fixture = raw.get("fixture")
    league = raw.get("league")
    teams = raw.get("teams")
    if not isinstance(fixture, dict) or not isinstance(league, dict) or not isinstance(teams, dict):
        return None, "FIXTURE_ENVELOPE_INCOMPLETE"

    fixture_id = _positive_int(fixture.get("id"))
    league_id = _positive_int(league.get("id"))
    home = teams.get("home")
    away = teams.get("away")
    status = fixture.get("status")
    if (
        fixture_id is None
        or league_id is None
        or not isinstance(home, dict)
        or not isinstance(away, dict)
        or not isinstance(status, dict)
    ):
        return None, "FIXTURE_IDENTITY_INCOMPLETE"

    home_id = _positive_int(home.get("id"))
    away_id = _positive_int(away.get("id"))
    start = _parse_aware_iso(fixture.get("date"))
    status_short = str(status.get("short") or "").strip().upper()
    if home_id is None or away_id is None or start is None or not status_short:
        return None, "FIXTURE_CORE_FIELDS_INCOMPLETE"

    if status_short not in FUTURE_STATUSES:
        return None, "FIXTURE_NOT_FUTURE_SCHEDULED"
    if start <= captured_at:
        return None, "FIXTURE_NOT_STRICTLY_FUTURE"

    home_name = str(home.get("name") or "").strip()
    away_name = str(away.get("name") or "").strip()
    league_name = str(league.get("name") or "").strip()
    country = str(league.get("country") or "").strip()
    if not home_name or not away_name or not league_name:
        return None, "FIXTURE_NAMES_INCOMPLETE"

    return {
        "provider": "api_football",
        "provider_fixture_id": str(fixture_id),
        "provider_league_id": str(league_id),
        "provider_home_team_id": str(home_id),
        "provider_away_team_id": str(away_id),
        "event_start_utc": start.isoformat(),
        "status_short": status_short,
        "competition": league_name,
        "country": country,
        "season": league.get("season"),
        "round": league.get("round"),
        "home_team": home_name,
        "away_team": away_name,
        "venue_id": (
            str(fixture.get("venue", {}).get("id"))
            if isinstance(fixture.get("venue"), dict) and fixture.get("venue", {}).get("id") is not None
            else None
        ),
        "venue_name": (
            str(fixture.get("venue", {}).get("name") or "").strip() or None
            if isinstance(fixture.get("venue"), dict)
            else None
        ),
        "timezone": str(fixture.get("timezone") or "").strip() or None,
    }, None


def run_capture(
    *,
    api_key: str,
    out_dir: Path,
    target_date: str,
    session: Any | None = None,
    captured_at_utc: str | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    try:
        key.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("API_FOOTBALL_KEY_MUST_BE_ASCII") from error

    captured_at = (
        _parse_aware_iso(captured_at_utc)
        if captured_at_utc is not None
        else datetime.now(timezone.utc)
    )
    if captured_at is None:
        raise ValueError("CAPTURED_AT_UTC_INVALID")
    captured_at = captured_at.replace(microsecond=0)

    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("TARGET_DATE_INVALID") from error

    out_dir.mkdir(parents=True, exist_ok=True)
    url = BASE_URL + ENDPOINT
    params = {"date": target_date, "timezone": TIMEZONE_NAME}
    client = session or requests.Session()

    request_meta = {
        "method": "GET",
        "url": url,
        "params": params,
        "headers": {"x-apisports-key": "REDACTED"},
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    _write_json(out_dir / "request.json", request_meta)

    response = client.get(
        url,
        headers={"x-apisports-key": key},
        params=params,
        timeout=TIMEOUT_SECONDS,
    )
    body = bytes(response.content)
    (out_dir / "response_body.bin").write_bytes(body)

    public_headers = {
        name.lower(): value
        for name, value in response.headers.items()
        if name.lower() in PUBLIC_HEADER_ALLOWLIST
    }
    _write_json(out_dir / "response_headers_public.json", public_headers)

    parsed = response.json()
    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    raw_rows = parsed.get("response") if isinstance(parsed, dict) else None
    if not (200 <= int(response.status_code) < 300):
        raise ValueError(f"API_FOOTBALL_HTTP_STATUS_{response.status_code}")
    if errors not in ({}, [], None):
        raise ValueError("API_FOOTBALL_PROVIDER_ERRORS")
    if not isinstance(raw_rows, list):
        raise ValueError("API_FOOTBALL_FIXTURES_RESPONSE_INVALID")

    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_rows):
        event, blocker = _event_projection(row, captured_at=captured_at)
        if event is not None:
            eligible.append(event)
        else:
            blocked.append({"index": idx, "blocker": blocker})

    eligible.sort(key=lambda row: (row["event_start_utc"], int(row["provider_fixture_id"])))
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    deduped: list[dict[str, Any]] = []
    for row in eligible:
        fixture_id = row["provider_fixture_id"]
        if fixture_id in seen:
            duplicate_ids.append(fixture_id)
            continue
        seen.add(fixture_id)
        deduped.append(row)

    registry = {
        "schema": "MATRIX_API_FOOTBALL_FUTURE_FIXTURE_REGISTRY_V1",
        "provider": "api_football",
        "captured_at_utc": captured_at.isoformat(),
        "target_date": target_date,
        "provider_timezone": TIMEZONE_NAME,
        "future_only": True,
        "strict_future_cutoff_utc": captured_at.isoformat(),
        "fixtures_received": len(raw_rows),
        "eligible_future_fixtures": len(deduped),
        "blocked_or_nonfuture_rows": len(blocked),
        "duplicate_fixture_ids": duplicate_ids,
        "events": deduped,
        "protections": {
            "outcomes_used": False,
            "odds_used": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    _write_json(out_dir / "future_fixture_registry.json", registry)

    manifest = {
        "schema": "MATRIX_API_FOOTBALL_REAL_FIXTURE_CAPTURE_V1",
        "provider": "api_football",
        "endpoint": ENDPOINT,
        "captured_at_utc": captured_at.isoformat(),
        "target_date": target_date,
        "provider_timezone": TIMEZONE_NAME,
        "network_call_performed": True,
        "provider_response_received": True,
        "verified_successful_provider_response": True,
        "http_status": int(response.status_code),
        "response_bytes": len(body),
        "response_sha256": _sha256(body),
        "raw_response_persisted": True,
        "fixtures_received": len(raw_rows),
        "eligible_future_fixtures": len(deduped),
        "blocked_or_nonfuture_rows": len(blocked),
        "duplicate_fixture_ids": duplicate_ids,
        "rate_limit": {
            "daily_limit": public_headers.get("x-ratelimit-requests-limit"),
            "daily_remaining": public_headers.get("x-ratelimit-requests-remaining"),
            "minute_limit": public_headers.get("x-ratelimit-limit"),
            "minute_remaining": public_headers.get("x-ratelimit-remaining"),
        },
        "status": "PASS",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    _write_json(out_dir / "capture_manifest.json", manifest)
    return manifest


def default_target_date(now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    bogota_today = now.astimezone(ZoneInfo(TIMEZONE_NAME)).date()
    return (bogota_today + timedelta(days=1)).isoformat()


def main() -> None:
    target_date = os.environ.get("MATRIX_API_FOOTBALL_TARGET_DATE", "").strip() or default_target_date()
    out_dir = Path(
        os.environ.get(
            "MATRIX_API_FOOTBALL_FIXTURE_DIR",
            "evidence/api_football/fixtures",
        )
    )
    result = run_capture(
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        out_dir=out_dir,
        target_date=target_date,
    )
    print(
        json.dumps(
            {
                "provider": result["provider"],
                "endpoint": result["endpoint"],
                "target_date": result["target_date"],
                "fixtures_received": result["fixtures_received"],
                "eligible_future_fixtures": result["eligible_future_fixtures"],
                "daily_remaining": result["rate_limit"]["daily_remaining"],
                "status": result["status"],
                "real_money": result["real_money"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
