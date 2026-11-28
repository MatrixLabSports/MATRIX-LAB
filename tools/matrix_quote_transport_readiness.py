"""Read-only diagnostic of real quote transport vs apparent scheduler success.

No bookmaker/API odds requests, no GUI automation and no betting.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
Q = "evidence/notifications/telegram/MATRIX_ODDS_API_QUOTA_GUARD_LAST.json"
H = "evidence/notifications/telegram/MATRIX_SELF_HOSTED_BROWSER_HEALTH_LAST.json"
C = "evidence/notifications/telegram/MATRIX_BROWSER_CDP_COLLECTION_LAST.json"
OUT = "evidence/notifications/telegram/MATRIX_QUOTE_TRANSPORT_READINESS_LAST.json"
RUN_URL = ("https://api.github.com/repos/MatrixLabSports/MATRIX-LAB/actions/"
           "workflows/matrix-selfhosted-browser-quotes-5m.yml/runs?per_page=10")


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError, UnicodeError):
        return None


def utc(value: str):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("MISSING_RUN_TIMESTAMP_ZONE")
    return parsed.astimezone(timezone.utc)


def build(*, quota: dict | None, browser_health: dict | None,
          browser_collection: dict | None, workflow_runs: dict | None,
          checked_at: datetime) -> dict:
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("AWARE_CHECK_TIME_REQUIRED")
    now = checked_at.astimezone(timezone.utc)
    blocked = quota is None or (quota.get("decision") or {}).get("api_calls_allowed") is not True
    monthly = (quota or {}).get("http_status") == 429 and (
        (quota or {}).get("decision") or {}).get("stage") == "BLOCKED_EXHAUSTED"
    health_verified = False
    health_age = None
    if browser_health and browser_health.get("status") == "PASS_CDP_REACHABLE":
        try:
            age = (now - utc(browser_health["checked_at_utc"])).total_seconds() / 60
            health_age = round(age, 2)
            health_verified = 0 <= age <= 15
        except (ValueError, KeyError, TypeError):
            pass
    collection_verified = False
    collection_age = None
    if browser_collection:
        try:
            timestamp = browser_collection.get("captured_at_utc") or browser_collection.get("generated_at_utc")
            age = (now - utc(timestamp)).total_seconds() / 60
            collection_age = round(age, 2)
            # A successful browser read is required before asking the quote
            # validator to assess exact event/market/selection freshness.
            collection_verified = 0 <= age <= 15 and (
                browser_collection.get("status") in ("PASS", "PASS_CAPTURED", "CAPTURED")
            )
        except (ValueError, KeyError, TypeError):
            pass
    runs = (workflow_runs or {}).get("workflow_runs") or []
    run_info = []
    for row in runs[:10]:
        if not isinstance(row, dict):
            continue
        try:
            age_min = round((now - utc(row["created_at"])).total_seconds()/60, 2)
            item = {"run_id": row["id"], "status": row["status"],
                    "conclusion": row.get("conclusion"), "created_at": row["created_at"],
                    "age_minutes": age_min}
            run_info.append(item)
        except (ValueError, TypeError, KeyError):
            continue
    stalled = [x for x in run_info if x["status"] in ("queued", "pending") and x["age_minutes"] > 15]
    problems = []
    if blocked:
        problems.append("NO_AUTHORIZED_ODDS_API_NET_REQUESTS")
    if monthly:
        problems.append("LAST_VERIFIED_ODDS_API_NET_MONTHLY_QUOTA_EXCEEDED")
    if not health_verified:
        problems.append("NO_RECENT_PHYSICAL_CDP_BROWSER_HEALTH_PROOF")
    if not collection_verified:
        problems.append("NO_RECENT_PHYSICAL_BROWSER_QUOTE_COLLECTION_PROOF")
    if stalled:
        problems.append("SELF_HOSTED_WORKFLOW_QUEUE_OLDER_THAN_15_MINUTES")
    result = {
        "schema": "MATRIX_QUOTE_TRANSPORT_READINESS_V1",
        "checked_at_utc": now.isoformat(),
        "status": "NO_GO_REAL_QUOTE_TRANSPORT_NOT_CERTIFIED" if problems else
                  "READINESS_INFRASTRUCTURE_ONLY_EXACT_QUOTES_UNCERTIFIED",
        "odds_api_http_status": (quota or {}).get("http_status"),
        "odds_api_stage": ((quota or {}).get("decision") or {}).get("stage"),
        "odds_api_requests_allowed": not blocked,
        "browser_health_status": (browser_health or {}).get("status"),
        "browser_health_age_minutes": health_age,
        "browser_health_fresh_15m": health_verified,
        "browser_collection_status": (browser_collection or {}).get("status"),
        "browser_collection_age_minutes": collection_age,
        "browser_collection_fresh_15m": collection_verified,
        "self_hosted_workflow_runs_checked": run_info,
        "stalled_self_hosted_run_ids": [x["run_id"] for x in stalled],
        "runner_offline_proven": False,
        "runner_missing_or_busy_possibilities_not_asserted_as_facts": True,
        "failures": problems,
        "no_cdp_or_browser_requests_made_by_this_diagnostic": True,
        "no_odds_provider_calls_made_by_this_diagnostic": True,
        "telegram_messages_sent": 0,
        "exact_bookmaker_over25_quotes_verified_by_this_diagnostic": 0,
        "signal_emission_authorized": False,
        "model_probability_modified": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return result


def query_workflow_runs(token: str) -> dict | None:
    if not token:
        return None
    request = Request(RUN_URL, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=15) as response:
            content = response.read(400_000)
        parsed = json.loads(content.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, UnicodeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT/OUT)
    args = parser.parse_args()
    result = build(
        quota=read_json(ROOT/Q),
        browser_health=read_json(ROOT/H),
        browser_collection=read_json(ROOT/C),
        workflow_runs=query_workflow_runs(os.environ.get("GITHUB_TOKEN", "")),
        checked_at=datetime.now(timezone.utc),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)+"\n",
                        encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
