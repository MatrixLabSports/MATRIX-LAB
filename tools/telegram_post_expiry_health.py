"""Read-only post-expiry Telegram supervisor health. No provider or Telegram calls."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.football_subscription_deadline_guard import evaluate

BOGOTA = ZoneInfo("America/Bogota")
OUTPUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_POST_EXPIRY_HEALTH_LAST.json")
WORKFLOW = Path(".github/workflows/telegram-green-signals.yml")
SUPERVISOR = Path("tools/telegram_green_signal_alerts.py")


def build(as_of_bogota: datetime, workflow_text: str, supervisor_text: str) -> dict:
    if as_of_bogota.tzinfo is None or as_of_bogota.utcoffset() is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    date_bogota = as_of_bogota.astimezone(BOGOTA).date()
    subscription = evaluate(date_bogota)
    schedule_present = 'cron: "7,22,37,52 * * * *"' in workflow_text
    workflow_paid_guard = "football_subscription_deadline_guard --require-paid-use --require-key" in workflow_text
    supervisor_paid_guard = 'MATRIX_API_FOOTBALL_AUTHORIZED' in supervisor_text
    supervisor_paid_quote_call = "primary_offer = exact_over25_offer(" in supervisor_text
    blocked = not subscription["paid_window_active"] and not subscription["post_cutoff_override"]
    return {
        "schema": "MATRIX_TELEGRAM_POST_EXPIRY_HEALTH_V1",
        "as_of_bogota": as_of_bogota.astimezone(BOGOTA).isoformat(),
        "paid_api": subscription["status"],
        "schedule_15m_configured": schedule_present,
        "scheduled_supervisor_blocked_by_paid_gate": blocked and workflow_paid_guard,
        "workflow_requires_paid_api": workflow_paid_guard,
        "supervisor_requires_explicit_paid_authorization": supervisor_paid_guard,
        "supervisor_contains_paid_quote_call": supervisor_paid_quote_call,
        "telegram_send_acknowledged": False,
        "telegram_delivery_certified": False,
        "independent_provider_calls": 0,
        "paid_provider_calls": 0,
        "status": "POST_EXPIRY_SUPERVISOR_BLOCKED_FAIL_CLOSED" if blocked and workflow_paid_guard else "REVIEW_REQUIRED",
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main() -> None:
    report = build(datetime.now(BOGOTA), WORKFLOW.read_text(encoding="utf-8"),
                   SUPERVISOR.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
