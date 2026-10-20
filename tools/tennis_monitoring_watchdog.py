from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_AGE_MINUTES = 30
WORKFLOWS = {
    "hard": "tennis-hard-governed-day-resolution.yml",
    "clay": "tennis-clay-daily-prospective.yml",
    "live": "live-tennis-cumulative-gate-reconcile.yml",
}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def evaluate_runs(runs: list[dict[str, Any]], now: datetime, max_age_minutes: int = MAX_AGE_MINUTES) -> dict[str, Any]:
    if not runs:
        return {"status": "FAIL", "reason": "NO_RUNS_FOUND", "age_minutes": None}

    ordered = sorted(runs, key=lambda x: parse_dt(str(x.get("created_at") or "1970-01-01T00:00:00Z")), reverse=True)
    latest = ordered[0]
    created = parse_dt(str(latest.get("created_at")))
    age = (now - created).total_seconds() / 60.0

    if age > max_age_minutes:
        return {
            "status": "FAIL",
            "reason": "LATEST_RUN_STALE",
            "age_minutes": round(age, 2),
            "latest_run_id": latest.get("id"),
            "latest_status": latest.get("status"),
            "latest_conclusion": latest.get("conclusion"),
        }

    status = str(latest.get("status") or "")
    conclusion = latest.get("conclusion")
    if status == "completed" and conclusion not in {"success", "neutral", "skipped"}:
        newer_active = next(
            (r for r in ordered if str(r.get("status") or "") in {"queued", "pending", "in_progress", "waiting", "requested"}),
            None,
        )
        if newer_active is None:
            return {
                "status": "FAIL",
                "reason": "LATEST_TERMINAL_RUN_FAILED",
                "age_minutes": round(age, 2),
                "latest_run_id": latest.get("id"),
                "latest_status": status,
                "latest_conclusion": conclusion,
            }

    return {
        "status": "PASS",
        "reason": "RECENT_RUN_PRESENT",
        "age_minutes": round(age, 2),
        "latest_run_id": latest.get("id"),
        "latest_status": status,
        "latest_conclusion": conclusion,
        "latest_event": latest.get("event"),
    }


def fetch_runs(repo: str, workflow: str, token: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=10"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "MATRIX-Tennis-Monitoring-Watchdog",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("workflow_runs") or []


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-age-minutes", type=int, default=MAX_AGE_MINUTES)
    a = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    now = datetime.now(timezone.utc)
    checks: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []

    for lane, workflow in WORKFLOWS.items():
        try:
            runs = fetch_runs(a.repo, workflow, token)
            result = evaluate_runs(runs, now, a.max_age_minutes)
        except Exception as exc:
            result = {"status": "FAIL", "reason": "GITHUB_API_ERROR", "error": f"{type(exc).__name__}:{exc}"}
        result["workflow"] = workflow
        checks[lane] = result
        if result["status"] != "PASS":
            failures.append({"lane": lane, **result})

    report = {
        "schema": "MATRIX_TENNIS_MONITORING_WATCHDOG_V1",
        "generated_at_utc": now.isoformat(),
        "policy": {
            "expected_cadence_minutes": 15,
            "max_run_age_minutes": int(a.max_age_minutes),
            "default_branch_scheduler_required": True,
            "real_money": "BLOCKED",
        },
        "checks": checks,
        "summary": {
            "status": "PASS" if not failures else "FAIL_CLOSED",
            "failures": len(failures),
            "lanes_checked": len(checks),
        },
        "failures": failures,
    }

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
