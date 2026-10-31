from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BLOCKER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json")
READINESS = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_FINAL_WINDOW_READINESS_LAST.json")
QUOTE_AUDIT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json")
SUPERVISOR_WORKFLOW = Path(".github/workflows/telegram-matrix-supervisor-15m.yml")
GREEN_WORKFLOW = Path(".github/workflows/telegram-green-signals.yml")
OUTPUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_RECOVERY_GUARD_LAST.json")

SUPERVISOR_MINUTES = (0, 15, 30, 45)
GREEN_MINUTES = (7, 22, 37, 52)
COMBINED_MINUTES = tuple(sorted(set(SUPERVISOR_MINUTES + GREEN_MINUTES)))
FINAL_WINDOW_MINUTES = 120
MAX_COMBINED_NOMINAL_GAP_MINUTES = 8


def parse_dt(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_DATETIME")
    return dt.astimezone(timezone.utc)


def schedule_gaps(minutes: tuple[int, ...]) -> list[int]:
    ordered = sorted(set(int(x) for x in minutes))
    if not ordered:
        return [60]
    return [
        ((ordered[(i + 1) % len(ordered)] - ordered[i]) % 60) or 60
        for i in range(len(ordered))
    ]


def next_combined_cycle(at: datetime) -> datetime:
    at = at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    hour = at.replace(minute=0)
    candidates = [hour + timedelta(minutes=m) for m in COMBINED_MINUTES]
    candidates += [hour + timedelta(hours=1, minutes=m) for m in COMBINED_MINUTES]
    return min(x for x in candidates if x >= at)


def _workflow_contract(path: Path, expected_cron: str) -> bool:
    text = path.read_text(encoding="utf-8")
    return expected_cron in text and "python -m tools.telegram_green_signal_alerts" in text


def build(
    blocker: dict[str, Any],
    readiness: dict[str, Any],
    quote_audit: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    waiting = [
        row for row in (blocker.get("records") or [])
        if isinstance(row, dict) and row.get("gate_state") == "WAITING_FINAL_REVALIDATION_WINDOW"
    ]
    checks = []
    failures = []
    for row in waiting:
        kickoff = parse_dt(row["kickoff"])
        window_open = kickoff - timedelta(minutes=FINAL_WINDOW_MINUTES)
        next_cycle = next_combined_cycle(window_open)
        delay_seconds = int((next_cycle - window_open).total_seconds())
        covered = delay_seconds <= MAX_COMBINED_NOMINAL_GAP_MINUTES * 60 and next_cycle < kickoff
        item = {
            "fixture_id": str(row.get("fixture_id") or ""),
            "match": row.get("match"),
            "kickoff_utc": kickoff.isoformat(),
            "window_opens_utc": window_open.isoformat(),
            "next_combined_nominal_cycle_utc": next_cycle.isoformat(),
            "seconds_after_window_open": delay_seconds,
            "dual_cadence_window_covered": covered,
        }
        checks.append(item)
        if not covered:
            failures.append({
                "fixture_id": item["fixture_id"],
                "code": "DUAL_CADENCE_FINAL_WINDOW_COVERAGE_GAP",
            })

    schedule_contract = {
        "supervisor_cron_present": _workflow_contract(SUPERVISOR_WORKFLOW, 'cron: "*/15 * * * *"'),
        "green_cron_present": _workflow_contract(GREEN_WORKFLOW, 'cron: "7,22,37,52 * * * *"'),
        "combined_nominal_minutes": list(COMBINED_MINUTES),
        "combined_nominal_gaps_minutes": schedule_gaps(COMBINED_MINUTES),
        "maximum_combined_nominal_gap_minutes": max(schedule_gaps(COMBINED_MINUTES)),
    }
    if not schedule_contract["supervisor_cron_present"]:
        failures.append({"code": "SUPERVISOR_15M_CONTRACT_MISSING"})
    if not schedule_contract["green_cron_present"]:
        failures.append({"code": "GREEN_STAGGERED_15M_CONTRACT_MISSING"})
    if schedule_contract["maximum_combined_nominal_gap_minutes"] > MAX_COMBINED_NOMINAL_GAP_MINUTES:
        failures.append({"code": "COMBINED_NOMINAL_GAP_EXCEEDS_8_MINUTES"})

    sample = quote_audit.get("sample") or {}
    recommendation = quote_audit.get("recommendation_gate") or {}
    earliest = min((parse_dt(x["window_opens_utc"]) for x in checks), default=None)
    return {
        "schema": "MATRIX_TELEGRAM_SIGNAL_RECOVERY_GUARD_V1",
        "generated_at_utc": generated_at.isoformat(),
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "purpose": "Preserve final-window signal recovery without lowering model, EV, price, sharp-reference, or safety gates.",
        "schedule_contract": schedule_contract,
        "current_state": {
            "waiting_final_window_candidates": len(waiting),
            "earliest_window_open_utc": earliest.isoformat() if earliest else None,
            "dual_cadence_covered_candidates": sum(1 for x in checks if x["dual_cadence_window_covered"]),
            "readiness_status": readiness.get("status"),
            "real_quote_attempts_total": sample.get("real_quote_attempts_total"),
            "remaining_to_quote_minimum": sample.get("remaining_to_minimum"),
            "quote_recommendation_authorized": recommendation.get("recommendation_authorized"),
        },
        "governance": {
            "final_prematch_window_minutes": FINAL_WINDOW_MINUTES,
            "odds_must_be_gt_1_50": True,
            "ev_must_be_positive": True,
            "p_matrix_must_preexist_before_odds": True,
            "pinnacle_freshness_gate_seconds": 120,
            "no_backfill_after_kickoff": True,
            "lower_gates_to_force_signals": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "interpretation": {
            "waiting_before_window_is_not_a_delivery_failure": True,
            "zero_quote_checks_before_window_is_expected": True,
            "quote_coverage_remains_structural_bottleneck": True,
            "dual_cadence_is_resilience_not_permission_to_send": True,
        },
        "failures": failures,
        "candidates": checks,
    }


def main() -> None:
    blocker = json.loads(BLOCKER.read_text(encoding="utf-8"))
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    quote_audit = json.loads(QUOTE_AUDIT.read_text(encoding="utf-8"))
    report = build(blocker, readiness, quote_audit)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        **report["current_state"],
        "maximum_combined_nominal_gap_minutes": report["schedule_contract"]["maximum_combined_nominal_gap_minutes"],
    }, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
