"""Read-only MATRIX supervisor diagnostics: no HTTP, no Telegram, no paid APIs.

Run: python -m tools.matrix_telegram_offline_diagnostics
This is discovery-only; it cannot certify live quote revalidation or delivery.
"""
from __future__ import annotations

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
    return {
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
    print(json.dumps(collect(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
