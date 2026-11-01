"""Read-only health check for Telegram's canonical upstream inputs.

No provider calls, no secrets, no Telegram messages. Exit 2 when both sports
have no canonical JSON files for today/tomorrow (Bogotá).
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def inspect(root: Path, today: str, tomorrow: str) -> dict:
    dates = (today, tomorrow)
    football_patterns = ("browser_physical_verification/*.json", "shadow_quote_freeze/*.json", "over25_shadow_ev/*.json")
    football = {day: {pattern: len(list((root / "evidence/api_football/daily_prematch_reports" / day).glob(pattern))) for pattern in football_patterns} for day in dates}
    tennis = {day: len(list((root / "evidence/tennis_signals" / day).glob("*.json"))) for day in dates}
    total = sum(sum(counts.values()) for counts in football.values()) + sum(tennis.values())
    return {
        "schema": "MATRIX_TELEGRAM_CANONICAL_INPUT_HEALTH_V1",
        "dates_bogota": list(dates),
        "football_files": football,
        "tennis_files": tennis,
        "total_canonical_files": total,
        "status": "INPUTS_PRESENT_NOT_SIGNAL_CERTIFIED" if total else "FAIL_CLOSED_NO_CANONICAL_INPUTS",
        "provider_calls": 0,
        "telegram_messages_sent": 0,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main() -> int:
    now = datetime.now(ZoneInfo("America/Bogota")).date()
    result = inspect(Path("."), now.isoformat(), (now + timedelta(days=1)).isoformat())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["total_canonical_files"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
