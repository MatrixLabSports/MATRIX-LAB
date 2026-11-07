"""Static, network-free certification of expired paid-source dependencies.

Read-only diagnostic. Does not unlock or call any bookmaker, API or Telegram.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/telegram-green-signals.yml"
SUPERVISOR = ROOT / "tools/telegram_green_signal_alerts.py"
OUT = ROOT / "evidence/governance/MATRIX_TELEGRAM_PAID_SOURCE_STATIC_AUDIT_LAST.json"


def audit(workflow: str, supervisor: str) -> dict:
    checks = {
        "schedule_15m_configured": 'cron: "7,22,37,52 * * * *"' in workflow,
        "paid_subscription_pre_supervisor_gate": "python -m tools.football_subscription_deadline_guard --require-paid-use --require-key" in workflow,
        "paid_secret_required_by_workflow": 'test -n "$API_FOOTBALL_KEY"' in workflow,
        "paid_authorization_required_by_supervisor": 'API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED' in supervisor,
        "paid_key_required_by_supervisor": 'API_FOOTBALL_KEY_NOT_CONFIGURED' in supervisor,
        "paid_quote_transport_exact": '"https://v3.football.api-sports.io/odds"' in supervisor,
        "paid_quote_http_guard": "paid_football_quote_transport_allowed()" in supervisor,
    }
    return {
        "schema": "MATRIX_TELEGRAM_PAID_SOURCE_STATIC_AUDIT_V1",
        "as_of_bogota": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "checks": checks,
        "independent_live_signal_supervisor_certified": False,
        "telegram_delivery_ack_certified": False,
        "provider_calls": 0,
        "telegram_calls": 0,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
        "verdict": "PAID_SOURCE_DEPENDENCIES_REMAIN_FAIL_CLOSED" if all(checks.values()) else "MANUAL_REVIEW_REQUIRED",
        "limitations": [
            "Static checks do not prove runtime scheduler delivery.",
            "Paid source dependency must not be removed without a verified alternative data path.",
            "No valid Telegram Bot API acknowledgment is present in this audit.",
        ],
    }


def main() -> None:
    result = audit(WORKFLOW.read_text(encoding="utf-8"), SUPERVISOR.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["verdict"] != "PAID_SOURCE_DEPENDENCIES_REMAIN_FAIL_CLOSED":
        raise SystemExit("PAID_SOURCE_STATIC_AUDIT_UNCERTAIN")


if __name__ == "__main__":
    main()
