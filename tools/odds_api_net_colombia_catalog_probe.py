from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://api.odds-api.net/v1"
ENDPOINT = "/bookmakers"
TIMEOUT_SECONDS = 20.0
REQUIRED_BOOKMAKERS = ("rushbet", "betplay", "betano", "bwin")


def _rate(headers: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "limit": headers.get("X-RateLimit-Limit"),
        "remaining": headers.get("X-RateLimit-Remaining"),
        "bucket": headers.get("X-RateLimit-Bucket"),
        "retry_after": headers.get("Retry-After"),
    }


def run(api_key: str, out_dir: Path, session: Any | None = None) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("ODDS_API_NET_KEY_NOT_CONFIGURED")
    key.encode("ascii")

    out_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    response = client.get(
        BASE_URL + ENDPOINT,
        headers={"X-API-Key": key, "Accept": "application/json"},
        params={"country_code": "CO"},
        timeout=TIMEOUT_SECONDS,
    )
    body = bytes(response.content)
    raw_path = out_dir / "colombia_bookmakers.bin"
    raw_path.write_bytes(body)

    try:
        payload = response.json()
    except Exception as exc:
        raise ValueError("ODDS_API_NET_INVALID_JSON") from exc

    items = payload.get("items") if isinstance(payload, Mapping) else None
    valid_items = [x for x in items if isinstance(x, Mapping)] if isinstance(items, list) else []
    bookmaker_keys = sorted({
        str(item.get("bookmaker") or "").strip().casefold()
        for item in valid_items
        if str(item.get("bookmaker") or "").strip()
    })
    present = {name: name in bookmaker_keys for name in REQUIRED_BOOKMAKERS}
    all_required_present = all(present.values())
    http_ok = 200 <= int(response.status_code) < 300
    provider_pass = http_ok and isinstance(items, list) and all_required_present

    manifest = {
        "schema": "MATRIX_ODDS_API_NET_COLOMBIA_CATALOG_PROBE_V1",
        "provider": "odds_api_net",
        "base_url": BASE_URL,
        "endpoint": ENDPOINT,
        "country_code": "CO",
        "request_started_at_utc": started,
        "response_observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "http_status": int(response.status_code),
        "provider_rows": len(valid_items),
        "bookmaker_keys": bookmaker_keys,
        "required_bookmakers": list(REQUIRED_BOOKMAKERS),
        "required_presence": present,
        "all_required_present": all_required_present,
        "network_calls_performed": 1,
        "raw_path": str(raw_path),
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "raw_bytes": len(body),
        "rate_limit": _rate(response.headers),
        "automatic_wagering": False,
        "odds_used_to_generate_model_probability": False,
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
        os.environ.get("ODDS_API_NET_KEY", ""),
        Path("evidence/odds_api_net/colombia_catalog"),
    )
    print("ODDS_API_NET_COLOMBIA_CATALOG_GATE:", result["status"])
    print("provider_rows=", result["provider_rows"])
    print("rushbet_present=", result["required_presence"]["rushbet"])
    print("betplay_present=", result["required_presence"]["betplay"])
    print("betano_present=", result["required_presence"]["betano"])
    print("bwin_present=", result["required_presence"]["bwin"])
    print("rate_remaining=", result["rate_limit"]["remaining"])
    print("real_money=", result["real_money"])


if __name__ == "__main__":
    main()
