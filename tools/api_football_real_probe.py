from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT = "/countries"
TIMEOUT_SECONDS = 15.0

PUBLIC_HEADER_ALLOWLIST = (
    "content-type",
    "date",
    "x-ratelimit-requests-limit",
    "x-ratelimit-requests-remaining",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_probe(
    *,
    api_key: str,
    out_dir: Path,
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

    out_dir.mkdir(parents=True, exist_ok=True)
    captured_at = captured_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    url = BASE_URL + ENDPOINT
    client = session or requests.Session()

    request_meta = {
        "method": "GET",
        "url": url,
        "headers": {"x-apisports-key": "REDACTED"},
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    _write_json(out_dir / "request.json", request_meta)

    try:
        response = client.get(
            url,
            headers={"x-apisports-key": key},
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as error:
        evidence = {
            "schema": "MATRIX_API_FOOTBALL_REAL_PROBE_V1",
            "provider": "api_football",
            "base_url": BASE_URL,
            "endpoint": ENDPOINT,
            "captured_at_utc": captured_at,
            "secret_resolved": True,
            "network_call_attempted": True,
            "network_call_performed": False,
            "provider_response_received": False,
            "verified_successful_provider_response": False,
            "status": "NETWORK_ERROR",
            "error_type": type(error).__name__,
            "error": str(error),
            "raw_response_persisted": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
        _write_json(out_dir / "probe_manifest.json", evidence)
        return evidence

    body = bytes(response.content)
    (out_dir / "response_body.bin").write_bytes(body)

    public_headers = {
        name.lower(): value
        for name, value in response.headers.items()
        if name.lower() in PUBLIC_HEADER_ALLOWLIST
    }
    _write_json(out_dir / "response_headers_public.json", public_headers)

    parsed: Any = None
    parse_error: str | None = None
    try:
        parsed = response.json()
    except Exception as error:
        parse_error = f"{type(error).__name__}:{error}"

    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    results = parsed.get("results") if isinstance(parsed, dict) else None
    provider_response = parsed.get("response") if isinstance(parsed, dict) else None
    errors_clear = errors in ({}, [], None)
    results_positive = isinstance(results, int) and results > 0
    response_nonempty = isinstance(provider_response, list) and len(provider_response) > 0
    http_ok = 200 <= int(response.status_code) < 300
    verified = bool(http_ok and parse_error is None and errors_clear and results_positive and response_nonempty)

    evidence = {
        "schema": "MATRIX_API_FOOTBALL_REAL_PROBE_V1",
        "provider": "api_football",
        "base_url": BASE_URL,
        "endpoint": ENDPOINT,
        "captured_at_utc": captured_at,
        "secret_resolved": True,
        "network_call_attempted": True,
        "network_call_performed": True,
        "provider_response_received": True,
        "verified_successful_provider_response": verified,
        "http_status": int(response.status_code),
        "response_bytes": len(body),
        "response_sha256": _sha256(body),
        "raw_response_persisted": True,
        "public_response_headers_persisted": True,
        "provider_errors": errors,
        "provider_results": results,
        "provider_response_items": len(provider_response) if isinstance(provider_response, list) else None,
        "json_parse_error": parse_error,
        "rate_limit": {
            "daily_limit": public_headers.get("x-ratelimit-requests-limit"),
            "daily_remaining": public_headers.get("x-ratelimit-requests-remaining"),
            "minute_limit": public_headers.get("x-ratelimit-limit"),
            "minute_remaining": public_headers.get("x-ratelimit-remaining"),
        },
        "status": "PASS" if verified else "PROVIDER_RESPONSE_NOT_VERIFIED",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    _write_json(out_dir / "probe_manifest.json", evidence)
    return evidence


def main() -> None:
    out_dir = Path(os.environ.get(
        "MATRIX_API_FOOTBALL_PROBE_DIR",
        "evidence/api_football/real_probe",
    ))
    result = run_probe(
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        out_dir=out_dir,
    )
    print(json.dumps({
        "provider": result.get("provider"),
        "endpoint": result.get("endpoint"),
        "network_call_performed": result.get("network_call_performed"),
        "verified_successful_provider_response": result.get("verified_successful_provider_response"),
        "http_status": result.get("http_status"),
        "provider_results": result.get("provider_results"),
        "rate_limit": result.get("rate_limit"),
        "status": result.get("status"),
        "real_money": result.get("real_money"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
