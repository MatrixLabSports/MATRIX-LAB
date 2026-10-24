from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT = "/odds/bookmakers"
TIMEOUT_SECONDS = 20.0


def _rate(headers: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "daily_limit": headers.get("x-ratelimit-requests-limit"),
        "daily_remaining": headers.get("x-ratelimit-requests-remaining"),
        "minute_limit": headers.get("X-RateLimit-Limit"),
        "minute_remaining": headers.get("X-RateLimit-Remaining"),
    }


def run(api_key: str, out_dir: Path, session: Any | None = None) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")

    out_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    response = client.get(
        BASE_URL + ENDPOINT,
        headers={"x-apisports-key": key},
        timeout=TIMEOUT_SECONDS,
    )
    body = bytes(response.content)
    observed = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw_path = out_dir / "bookmakers.bin"
    raw_path.write_bytes(body)

    payload = response.json()
    errors = payload.get("errors") if isinstance(payload, Mapping) else None
    rows = payload.get("response") if isinstance(payload, Mapping) else None
    provider_error = errors not in ({}, [], None)
    valid_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []

    bookmakers: list[dict[str, Any]] = []
    for row in valid_rows:
        name = str(row.get("name") or "").strip()
        bookmaker_id = row.get("id")
        bookmakers.append({"id": bookmaker_id, "name": name})

    pinnacle_matches = [
        row for row in bookmakers
        if "pinnacle" in row["name"].casefold()
    ]
    provider_pass = (
        200 <= int(response.status_code) < 300
        and not provider_error
        and isinstance(rows, list)
    )

    manifest = {
        "schema": "MATRIX_API_FOOTBALL_BOOKMAKER_CATALOG_AUDIT_V1",
        "endpoint": ENDPOINT,
        "request_started_at_utc": started,
        "response_observed_at_utc": observed,
        "http_status": int(response.status_code),
        "provider_error": provider_error,
        "provider_errors": errors if provider_error else None,
        "provider_rows": len(valid_rows),
        "bookmakers": bookmakers,
        "pinnacle_found": bool(pinnacle_matches),
        "pinnacle_matches": pinnacle_matches,
        "network_calls_performed": 1,
        "raw_path": str(raw_path),
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "raw_bytes": len(body),
        "rate_limit": _rate(response.headers),
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS" if provider_pass else "BLOCKED",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    result = run(
        os.environ.get("API_FOOTBALL_KEY", ""),
        Path("evidence/api_football/bookmakers"),
    )
    print("API_FOOTBALL_BOOKMAKER_CATALOG_GATE:", result["status"])
    print("provider_rows=", result["provider_rows"])
    print("pinnacle_found=", str(result["pinnacle_found"]).lower())
    print("pinnacle_matches=", json.dumps(result["pinnacle_matches"], ensure_ascii=False))
    print("daily_remaining=", result["rate_limit"]["daily_remaining"])
    print("real_money=", result["real_money"])


if __name__ == "__main__":
    main()
