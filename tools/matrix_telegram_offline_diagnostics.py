"""Read-only MATRIX supervisor diagnostics: no HTTP, no Telegram, no paid APIs.

Run: python -m tools.matrix_telegram_offline_diagnostics
This is discovery-only; it cannot certify live quote revalidation or delivery.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import timedelta
from pathlib import Path

from tools import telegram_green_signal_alerts as supervisor


def collect() -> dict:
    started = time.monotonic()
    now = supervisor.now_utc()
    dates = [str(now.astimezone(supervisor.BOGOTA).date() + timedelta(days=n)) for n in (1, 0, -1)]
    football_roots = [supervisor.FOOTBALL_ROOT / d for d in dates]
    tennis_roots = [supervisor.TENNIS_ROOT / d for d in dates]
    t = time.monotonic()
    football = supervisor.discover_football(dates)
    football_ms = round((time.monotonic() - t) * 1000, 2)
    t = time.monotonic()
    tennis = supervisor.discover_tennis(dates)
    tennis_ms = round((time.monotonic() - t) * 1000, 2)
    states = {}
    for row in football.values():
        state = supervisor.prematch_revalidation_state(row, now)
        states[state] = states.get(state, 0) + 1
    future = states.get("READY_FOR_FINAL_REVALIDATION", 0) + states.get("WAITING_FINAL_REVALIDATION_WINDOW", 0)
    missing_future_source = not (supervisor.FOOTBALL_ROOT / dates[0]).is_dir()
    calendar_path = Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_CALENDAR_RECONCILIATION_LAST.json")
    watchlist_path = Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_WATCHLIST_LAST.json")
    prereg_path = Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_BROWSER_PREREGISTRY_LAST.json")
    upstream = {}
    for name, path in (("calendar", calendar_path), ("watchlist", watchlist_path), ("preregistry", prereg_path)):
        if not path.is_file():
            upstream[name] = {"status": "MISSING"}
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("NOT_JSON_OBJECT")
            target = payload.get("target_date_bogota")
            upstream[name] = {
                "status": "TARGET_DATE_CURRENT" if target == dates[1] else "TARGET_DATE_NOT_CURRENT",
                "target_date_bogota": target,
                "counts": payload.get("counts"),
                "source_counts": payload.get("source_counts"),
            }
        except (OSError, ValueError, UnicodeError):
            upstream[name] = {"status": "UNREADABLE"}
    calendar_to_signal_gap = (
        "UPSTREAM_CALENDAR_PRESENT_BUT_NO_FUTURE_SCORED_CANDIDATES"
        if future == 0 and upstream["calendar"]["status"] == "TARGET_DATE_CURRENT"
        else "NOT_ESTABLISHED"
    )
    return {
        "upstream_calendar_evidence": upstream,
        "calendar_to_signal_gap": calendar_to_signal_gap,
        "readiness_status": "BLOCKED_NO_FUTURE_FOOTBALL_CANDIDATES" if future == 0 else "FUTURE_CANDIDATES_PRESENT_NOT_QUOTE_VERIFIED",
        "future_football_candidates": future,
        "tomorrow_football_source_missing": missing_future_source,
        "schema": "MATRIX_TELEGRAM_OFFLINE_DISCOVERY_DIAGNOSTICS_V1",
        "observed_at_utc": now.isoformat(),
        "dates_bogota": dates,
        "status": "READ_ONLY_DISCOVERY_ONLY",
        "football_source_dates_present": [p.name for p in football_roots if p.is_dir()],
        "tennis_source_dates_present": [p.name for p in tennis_roots if p.is_dir()],
        "football_candidates": len(football),
        "tennis_candidates": len(tennis),
        "football_prematch_states": dict(sorted(states.items())),
        "football_discovery_ms": football_ms,
        "tennis_discovery_ms": tennis_ms,
        "total_elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        "network_calls_permitted": False,
        "telegram_send_permitted": False,
        "paid_api_calls_permitted": False,
        "ledger_writes_permitted": False,
        "full_supervisor_certified": False,
        "note": "Discovery from local evidence only; no live price, fresh sharp or Telegram delivery is validated.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only local discovery diagnostics")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence destination")
    args = parser.parse_args()
    report = collect()
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
