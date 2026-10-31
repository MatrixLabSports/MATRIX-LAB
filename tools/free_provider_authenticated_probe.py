from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

OUT = Path("evidence/governance/MATRIX_FREE_API_AUTHENTICATED_PROBE_20261006.json")
TIMEOUT = 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_json(url: str, headers: dict[str, str], params: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    response = requests.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
    body = bytes(response.content)
    meta = {
        "url": url,
        "params": params or {},
        "http_status": int(response.status_code),
        "response_bytes": len(body),
        "response_sha256": sha256_bytes(body),
        "content_type": response.headers.get("content-type"),
    }
    try:
        parsed = response.json()
    except Exception:
        parsed = {"_non_json": True}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    return parsed, meta


def main() -> None:
    football_key = os.environ.get("FOOTBALL_DATA_ORG_KEY", "").strip()
    tennis_key = os.environ.get("LIVE_TENNIS_API_KEY", "").strip()
    if not football_key:
        raise SystemExit("FOOTBALL_DATA_ORG_KEY_NOT_CONFIGURED")
    if not tennis_key:
        raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")

    football_payload, football_meta = get_json(
        "https://api.football-data.org/v4/competitions",
        {"X-Auth-Token": football_key},
    )
    football_competitions = football_payload.get("competitions")
    football_count = len(football_competitions) if isinstance(football_competitions, list) else None
    football_ok = football_meta["http_status"] == 200 and isinstance(football_competitions, list)

    tennis_usage, tennis_usage_meta = get_json(
        "https://api.livetennisapi.com/api/public/v1/usage",
        {"X-API-Key": tennis_key},
    )
    tennis_matches, tennis_matches_meta = get_json(
        "https://api.livetennisapi.com/api/public/v1/matches",
        {"X-API-Key": tennis_key},
        {"status": "upcoming", "limit": 5},
    )
    tennis_data = tennis_matches.get("data")
    tennis_count = len(tennis_data) if isinstance(tennis_data, list) else None
    tennis_ok = (
        tennis_usage_meta["http_status"] == 200
        and tennis_matches_meta["http_status"] == 200
        and isinstance(tennis_data, list)
    )

    payload = {
        "schema": "MATRIX_FREE_API_AUTHENTICATED_PROBE_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "providers": {
            "football_data_org": {
                "authenticated": football_ok,
                "auth_method": "X-Auth-Token",
                "endpoint": football_meta,
                "competitions_returned": football_count,
                "token_redacted": True,
            },
            "live_tennis_api": {
                "authenticated": tennis_ok,
                "auth_method": "X-API-Key",
                "usage_endpoint": tennis_usage_meta,
                "matches_endpoint": tennis_matches_meta,
                "upcoming_sample_count": tennis_count,
                "usage_response_keys": sorted(tennis_usage.keys()),
                "token_redacted": True,
            },
        },
        "promotion_gate": {
            "football_data_org_pass": football_ok,
            "live_tennis_api_pass": tennis_ok,
            "both_pass": football_ok and tennis_ok,
            "automatic_model_feed": False,
            "requires_separate_coverage_reconciliation_before_matrix_use": True,
        },
        "protections": {
            "secrets_persisted": False,
            "secrets_echoed": False,
            "metrics_opened": False,
            "odds_to_probability": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS" if football_ok and tennis_ok else "BLOCKED",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "football_authenticated": football_ok,
        "football_competitions_returned": football_count,
        "tennis_authenticated": tennis_ok,
        "tennis_upcoming_sample_count": tennis_count,
    }, sort_keys=True))

    if not (football_ok and tennis_ok):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
