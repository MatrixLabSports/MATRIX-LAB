from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

BASE_URL = "https://v3.football.api-sports.io"
BOOKMAKER_ID = 4
BOOKMAKER_NAME = "Pinnacle"
TIMEOUT_SECONDS = 20.0
MAX_REQUESTS = 120


def _parse_aware(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _rate(headers: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "daily_limit": headers.get("x-ratelimit-requests-limit"),
        "daily_remaining": headers.get("x-ratelimit-requests-remaining"),
        "minute_limit": headers.get("X-RateLimit-Limit"),
        "minute_remaining": headers.get("X-RateLimit-Remaining"),
    }


def _extract_markets(rows: list[Mapping[str, Any]]) -> tuple[set[str], int]:
    markets: set[str] = set()
    quotes = 0
    for item in rows:
        bookmakers = item.get("bookmakers")
        if not isinstance(bookmakers, list):
            continue
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, Mapping):
                continue
            if str(bookmaker.get("id")) != str(BOOKMAKER_ID):
                continue
            bets = bookmaker.get("bets")
            if not isinstance(bets, list):
                continue
            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                name = str(bet.get("name") or "").strip()
                if name:
                    markets.add(name)
                values = bet.get("values")
                if isinstance(values, list):
                    quotes += sum(1 for v in values if isinstance(v, Mapping))
    return markets, quotes


def run(
    api_key: str,
    registry_path: Path,
    out_dir: Path,
    *,
    session: Any | None = None,
    now: datetime | None = None,
    capture_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    clock = capture_clock or (lambda: datetime.now(timezone.utc))

    document = json.loads(registry_path.read_text(encoding="utf-8"))
    events = document.get("events")
    if not isinstance(events, list):
        raise ValueError("FUTURE_FIXTURE_REGISTRY_INVALID")

    targets = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        fixture_id = str(event.get("provider_fixture_id") or "").strip()
        kickoff = str(event.get("event_start_utc") or "").strip()
        if not fixture_id or not kickoff:
            continue
        if _parse_aware(kickoff) <= reference:
            continue
        targets.append(event)

    if len(targets) > MAX_REQUESTS:
        raise ValueError("PINNACLE_COVERAGE_REQUEST_BUDGET_EXCEEDED")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()

    results: list[dict[str, Any]] = []
    all_markets: set[str] = set()
    calls = 0
    last_rate: dict[str, str | None] = {}
    provider_errors = 0

    for event in targets:
        fixture_id = str(event["provider_fixture_id"])
        response = client.get(
            BASE_URL + "/odds",
            headers={"x-apisports-key": key},
            params={"fixture": fixture_id, "bookmaker": BOOKMAKER_ID},
            timeout=TIMEOUT_SECONDS,
        )
        calls += 1
        captured_at = clock().astimezone(timezone.utc)
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("CAPTURE_CLOCK_MUST_BE_TIMEZONE_AWARE")
        body = bytes(response.content)
        raw_path = raw_dir / f"fixture_{fixture_id}_pinnacle.bin"
        raw_path.write_bytes(body)
        payload = response.json()
        errors = payload.get("errors") if isinstance(payload, Mapping) else None
        rows = payload.get("response") if isinstance(payload, Mapping) else None
        provider_error = errors not in ({}, [], None)
        if provider_error:
            provider_errors += 1
        valid_rows = [x for x in rows if isinstance(x, Mapping)] if isinstance(rows, list) else []
        markets, quote_count = _extract_markets(valid_rows)
        all_markets.update(markets)
        has_odds = bool(valid_rows and quote_count > 0)
        last_rate = _rate(response.headers)
        results.append({
            "fixture_id": fixture_id,
            "kickoff_utc": event.get("event_start_utc"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "competition": event.get("competition"),
            "country": event.get("country"),
            "has_pinnacle_odds": has_odds,
            "market_count": len(markets),
            "quote_count": quote_count,
            "markets": sorted(markets),
            "http_status": int(response.status_code),
            "provider_error": provider_error,
            "captured_at_utc": captured_at.replace(microsecond=0).isoformat(),
            "raw_path": str(raw_path),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
        })

    covered = sum(1 for row in results if row["has_pinnacle_odds"])
    status = "PASS" if provider_errors == 0 else "BLOCKED"
    manifest = {
        "schema": "MATRIX_API_FOOTBALL_PINNACLE_COVERAGE_AUDIT_V1",
        "started_at_utc": reference.replace(microsecond=0).isoformat(),
        "completed_at_utc": clock().astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "capture_timestamp_scope": "PER_FIXTURE_RESPONSE",
        "bookmaker": {"id": BOOKMAKER_ID, "name": BOOKMAKER_NAME},
        "target_fixture_count": len(targets),
        "network_calls_performed": calls,
        "fixtures_with_pinnacle_odds": covered,
        "fixtures_without_pinnacle_odds": len(targets) - covered,
        "coverage_rate": (covered / len(targets)) if targets else None,
        "unique_market_count": len(all_markets),
        "unique_markets": sorted(all_markets),
        "provider_error_count": provider_errors,
        "last_rate_limit": last_rate,
        "fixtures": results,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": status,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    result = run(
        os.environ.get("API_FOOTBALL_KEY", ""),
        Path("evidence/api_football/fixtures/future_fixture_registry.json"),
        Path("evidence/api_football/pinnacle_coverage"),
    )
    print("API_FOOTBALL_PINNACLE_COVERAGE_GATE:", result["status"])
    print("target_fixture_count=", result["target_fixture_count"])
    print("fixtures_with_pinnacle_odds=", result["fixtures_with_pinnacle_odds"])
    print("fixtures_without_pinnacle_odds=", result["fixtures_without_pinnacle_odds"])
    print("coverage_rate=", result["coverage_rate"])
    print("unique_market_count=", result["unique_market_count"])
    print("network_calls=", result["network_calls_performed"])
    print("daily_remaining=", result["last_rate_limit"].get("daily_remaining"))
    print("real_money=", result["real_money"])


if __name__ == "__main__":
    main()
