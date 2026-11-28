"""One-request, read-only API-Football free-plan status probe.

Explicit manual opt-in required. Never accesses fixtures, odds, or paid data.
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

STATUS_URL = "https://v3.football.api-sports.io/status"

def summarize(payload: dict, headers: dict, status_code: int) -> dict:
    response = payload.get("response") if isinstance(payload, dict) else None
    subscription = response.get("subscription", {}) if isinstance(response, dict) else {}
    requests = response.get("requests", {}) if isinstance(response, dict) else {}
    return {
        "schema": "MATRIX_API_FOOTBALL_FREE_STATUS_PROBE_V1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": status_code,
        "subscription_plan": str(subscription.get("plan") or "UNKNOWN"),
        "subscription_end": str(subscription.get("end") or ""),
        "requests_limit_day": requests.get("limit_day"),
        "requests_current": requests.get("current"),
        "rate_limit_day": headers.get("x-ratelimit-requests-limit"),
        "rate_remaining_day": headers.get("x-ratelimit-requests-remaining"),
        "free_plan_confirmed": str(subscription.get("plan") or "").lower() == "free" and status_code == 200,
        "current_season_coverage_verified": False,
        "fixture_production_authorized_by_this_probe": False,
        "signals_authorized_by_this_probe": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
        "endpoint": "/status",
        "network_calls_maximum": 1,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-one-status-call", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("evidence/governance/MATRIX_API_FOOTBALL_FREE_STATUS_LAST.json"))
    args = parser.parse_args()
    if not args.allow_one_status_call:
        raise SystemExit("EXPLICIT_STATUS_PROBE_OPT_IN_REQUIRED")
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    request = Request(STATUS_URL, headers={"x-apisports-key": key}, method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            code = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
            data = json.loads(response.read(65536).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise SystemExit("STATUS_PROBE_FAILED_FAIL_CLOSED:" + type(exc).__name__)
    result = summarize(data, headers, code)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if not result["free_plan_confirmed"]:
        raise SystemExit("FREE_PLAN_NOT_CONFIRMED_FAIL_CLOSED")

if __name__ == "__main__":
    main()
