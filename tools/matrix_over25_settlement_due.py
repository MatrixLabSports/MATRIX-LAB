"""Bounded postmatch research settlement for the 5-minute Windows collector.

One authenticated result scan at most once every two hours, maximum two
provider calls. This never authorizes model promotion, quotes or Telegram.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tools.matrix_independent_over25_prematch_freeze import canonical, stamp
from tools.matrix_independent_over25_research_settlement import settle, REPORT

INTERVAL = timedelta(hours=2)

def is_due(root: Path, now: datetime) -> bool:
    if now.utcoffset() is None:
        raise ValueError("SETTLEMENT_CLOCK_MUST_HAVE_UTC_OFFSET")
    old = root / REPORT
    if not old.is_file():
        return True
    try:
        doc = json.loads(old.read_text(encoding="utf-8"))
        last = stamp(doc["checked_at_utc"])
        if last > now.astimezone(timezone.utc):
            raise ValueError("SETTLEMENT_REPORT_FUTURE_TIME")
        # Recovery exception: zero prior HTTP calls, integrity-blocked
        # forecasts, and ALL referenced source hashes now physically verified.
        # This cannot override a previous provider request's rate budget.
        if doc.get("http_calls") == 0 and any(
            isinstance(x, dict) and x.get("status") == "BLOCKED_INVALID_SOURCE"
            for x in doc.get("decisions", [])
        ):
            report_path = root / "evidence/football_world_inventory/MATRIX_OVER25_MISSING_SOURCE_EXACT_RESTORE_LAST.json"
            if report_path.is_file():
                restored = json.loads(report_path.read_text(encoding="utf-8"))
                count = restored.get("source_refs_checked")
                if (restored.get("schema") == "MATRIX_OVER25_MISSING_SOURCE_RESTORE_V1"
                    and isinstance(count, int) and count > 0
                    and restored.get("already_verified") == count
                    and restored.get("unrecoverable_source_count") == 0):
                    return True
        return now.astimezone(timezone.utc) - last >= INTERVAL
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        # Stale/unreadable prior report is never usable as proof that a
        # provider was called; a new bounded scan will replace it.
        return True

def execute(root: Path, now: datetime, token: str) -> dict:
    if os.environ.get("REAL_MONEY") != "BLOCKED" or os.environ.get("AUTO_BETTING") != "DISABLED":
        raise ValueError("SETTLEMENT_MONEY_GUARD_FAIL_CLOSED")
    if not is_due(root, now):
        return {"status":"RATE_GUARD_NOT_DUE",
                "http_calls":0,"telegram_signal_authorized":False,
                "real_money":"BLOCKED"}
    result = settle(root, now=now, token=token, max_calls=2)
    if (result["telegram_signal_authorized"] is not False
        or result["real_money"] != "BLOCKED" or result["http_calls"] > 2):
        raise ValueError("SETTLEMENT_REPORT_FAILED_SAFETY_CHECK")
    target = root / REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical(result))
    return {"status":"VERIFIED_RESEARCH_SETTLEMENT_CYCLE",
            "http_calls":result["http_calls"],
            "settled_total":result["settled_total"],
            "unique_fixture_count":result["unique_fixture_count"],
            "telegram_signal_authorized":False,"real_money":"BLOCKED"}

def main():
    report=execute(Path.cwd(),datetime.now(timezone.utc),
                   os.environ.get("FOOTBALL_DATA_ORG_TOKEN", ""))
    print(json.dumps(report, sort_keys=True))

if __name__ == "__main__":
    main()
