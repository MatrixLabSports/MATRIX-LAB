"""Fail-closed readiness gate for tennis calendar cross-source reconciliation."""
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SOFA = ROOT / "evidence/calendar/MATRIX_SOFASCORE_TENNIS_20261031_DISCOVERY.json"
FLASH = ROOT / "evidence/calendar/MATRIX_FLASHSCORE_TENNIS_UNDATED_DISCOVERY_20261030.json"


def readiness(sofa: dict, flash: dict, user_calendar_date: str | None = None) -> dict:
    if sofa.get("source") != "SOFASCORE" or flash.get("source") != "FLASHSCORE":
        raise ValueError("Unexpected calendar sources")
    if not isinstance(sofa.get("records"), list) or not isinstance(flash.get("records"), list):
        raise ValueError("Missing raw calendar records")
    date = sofa.get("date_label")
    if not isinstance(date, str) or not date:
        raise ValueError("Missing SofaScore date")
    # User-specified calendar date is capture context, NOT per-event certification.
    if user_calendar_date is not None and user_calendar_date != date:
        raise ValueError("User calendar date conflicts with SofaScore date")
    page_verified = flash.get("source_page_date_verified") is True and flash.get("calendar_date") == date
    contextual = user_calendar_date == date
    verified = page_verified or contextual
    return {
        "target_date": date,
        "sofascore_raw": len(sofa["records"]),
        "flashscore_raw": len(flash["records"]),
        "flashscore_date_verified": page_verified,
        "user_calendar_date": user_calendar_date,
        "capture_date_context_accepted": contextual,
        "event_dates_individually_verified": False,
        "cross_source_matching_permitted": verified,
        "matching_scope": "CANDIDATE_ONLY" if verified else "BLOCKED",
        "cross_source_matches_certified": 0,
        "signals_authorized": 0,
        "block_reason": None if verified else "FLASHSCORE_DATE_NOT_VERIFIED",
        "certification_block_reason": "INDIVIDUAL_EVENT_DATES_NOT_VERIFIED",
    }


def main() -> None:
    sofa = json.loads(SOFA.read_text(encoding="utf-8"))
    flash = json.loads(FLASH.read_text(encoding="utf-8"))
    print(json.dumps(readiness(sofa, flash, user_calendar_date="2026-10-31"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
