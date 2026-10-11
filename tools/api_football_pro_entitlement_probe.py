from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT = 20.0


def _probe(session: Any, key: str, params: dict[str, Any], raw_path: Path) -> dict[str, Any]:
    response = session.get(
        BASE_URL + "/fixtures",
        headers={"x-apisports-key": key},
        params=params,
        timeout=TIMEOUT,
    )
    body = bytes(response.content)
    raw_path.write_bytes(body)
    payload = response.json()
    errors = payload.get("errors") if isinstance(payload, Mapping) else None
    rows = payload.get("response") if isinstance(payload, Mapping) else None
    provider_error = errors not in ({}, [], None)
    return {
        "http_status": int(response.status_code),
        "provider_error": provider_error,
        "provider_errors": errors if provider_error else None,
        "provider_rows": len(rows) if isinstance(rows, list) else None,
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "raw_bytes": len(body),
        "status": "PASS" if 200 <= int(response.status_code) < 300 and not provider_error and isinstance(rows, list) else "BLOCKED",
    }


def run(api_key: str, out_dir: Path, session: Any | None = None) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")

    out_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    season = _probe(client, key, {"league": "5", "season": 2026, "timezone": "UTC"}, out_dir / "season_2026.bin")
    last20 = _probe(client, key, {"team": "1", "last": 20, "timezone": "UTC"}, out_dir / "team_1_last_20.bin")

    verified = season["status"] == "PASS" and last20["status"] == "PASS"
    manifest = {
        "schema": "MATRIX_API_FOOTBALL_PRO_ENTITLEMENT_PROBE_V1",
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "network_calls_performed": 2,
        "season_2026": season,
        "team_last_20": last20,
        "pro_entitlement_verified": verified,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS" if verified else "BLOCKED",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    result = run(
        os.environ.get("API_FOOTBALL_KEY", ""),
        Path("evidence/api_football/pro_entitlement_probe"),
    )
    print(json.dumps({
        "network_calls_performed": result["network_calls_performed"],
        "season_2026_status": result["season_2026"]["status"],
        "season_2026_rows": result["season_2026"]["provider_rows"],
        "team_last_20_status": result["team_last_20"]["status"],
        "team_last_20_rows": result["team_last_20"]["provider_rows"],
        "pro_entitlement_verified": result["pro_entitlement_verified"],
        "status": result["status"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
