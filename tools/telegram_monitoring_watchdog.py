from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
REPORT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_MONITORING_WATCHDOG_LAST.json")

MAX_SUPERVISOR_AGE_MINUTES = 35
CRITICAL_WINDOW_MINUTES = 30


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_watchdog(ledger: dict[str, Any], now: datetime) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    history = ledger.get("run_history") or []
    last_run = history[-1] if history else None
    last_run_dt = parse_dt((last_run or {}).get("run_at_utc"))
    age_minutes = None
    if last_run_dt is None:
        failures.append({"code": "SUPERVISOR_RUN_HISTORY_MISSING"})
    else:
        age_minutes = (now - last_run_dt).total_seconds() / 60.0
        if age_minutes > MAX_SUPERVISOR_AGE_MINUTES:
            failures.append({
                "code": "SUPERVISOR_STALE",
                "age_minutes": round(age_minutes, 2),
                "max_minutes": MAX_SUPERVISOR_AGE_MINUTES,
            })

    lifecycle = ledger.get("candidate_lifecycle") or {}
    active_future = 0
    critical_unresolved = 0
    monitoring_breaches = 0
    new_monitoring_breaches = 0

    for key, row in lifecycle.items():
        kickoff = parse_dt(row.get("kickoff"))
        if kickoff is None:
            warnings.append({"code": "LIFECYCLE_KICKOFF_MISSING", "signal_key": key})
            continue

        if row.get("monitoring_breach") is True:
            monitoring_breaches += 1
            detected = parse_dt(row.get("monitoring_breach_detected_at_utc"))
            if detected is None:
                warnings.append({
                    "code": "MONITORING_BREACH_TIMESTAMP_MISSING",
                    "signal_key": key,
                })
            elif last_run_dt is not None and detected >= last_run_dt:
                new_monitoring_breaches += 1

        if kickoff <= now:
            continue

        active_future += 1
        minutes_to_kickoff = (kickoff - now).total_seconds() / 60.0
        attempts = int(row.get("final_revalidation_attempts") or 0)
        terminal = row.get("first_terminal_state")
        sent = bool(row.get("sent_at_utc"))

        if minutes_to_kickoff <= CRITICAL_WINDOW_MINUTES and attempts <= 0 and not terminal and not sent:
            critical_unresolved += 1
            failures.append({
                "code": "CRITICAL_PREMATCH_WITHOUT_REVALIDATION",
                "signal_key": key,
                "fixture_id": row.get("fixture_id"),
                "match": row.get("match"),
                "kickoff": row.get("kickoff"),
                "minutes_to_kickoff": round(minutes_to_kickoff, 2),
            })

    if new_monitoring_breaches > 0:
        failures.append({
            "code": "NEW_MONITORING_BREACH_PRESENT",
            "count": new_monitoring_breaches,
        })

    return {
        "schema": "MATRIX_TELEGRAM_MONITORING_WATCHDOG_V1",
        "generated_at_utc": now.isoformat(),
        "policy": {
            "max_supervisor_age_minutes": MAX_SUPERVISOR_AGE_MINUTES,
            "critical_window_minutes": CRITICAL_WINDOW_MINUTES,
            "zero_new_monitoring_breaches_required": True,
            "real_money": "BLOCKED",
        },
        "summary": {
            "status": "PASS" if not failures else "FAIL_CLOSED",
            "last_supervisor_run_age_minutes": None if age_minutes is None else round(age_minutes, 2),
            "active_future_candidates": active_future,
            "critical_unresolved_candidates": critical_unresolved,
            "monitoring_breaches": monitoring_breaches,
            "new_monitoring_breaches": new_monitoring_breaches,
            "failures": len(failures),
            "warnings": len(warnings),
        },
        "failures": failures,
        "warnings": warnings,
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    if not LEDGER.exists():
        raise SystemExit("WATCHDOG_LEDGER_NOT_FOUND")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    report = evaluate_watchdog(ledger, now)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    if report["summary"]["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
