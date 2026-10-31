"""Fail-closed readiness gate for tennis calendar cross-source reconciliation."""
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SOFA = ROOT / "evidence/calendar/MATRIX_SOFASCORE_TENNIS_20261031_DISCOVERY.json"
FLASH = ROOT / "evidence/calendar/MATRIX_FLASHSCORE_TENNIS_UNDATED_DISCOVERY_20261030.json"


def readiness(sofa: dict, flash: dict) -> dict:
    if sofa.get("source") != "SOFASCORE" or flash.get("source") != "FLASHSCORE":
        raise ValueError("Unexpected calendar sources")
    if not isinstance(sofa.get("records"), list) or not isinstance(flash.get("records"), list):
        raise ValueError("Missing raw calendar records")
    date = sofa.get("date_label")
    if not isinstance(date, str) or not date:
        raise ValueError("Missing SofaScore date")
    verified = flash.get("source_page_date_verified") is True and flash.get("calendar_date") == date
    return {
        "target_date": date,
        "sofascore_raw": len(sofa["records"]),
        "flashscore_raw": len(flash["records"]),
        "flashscore_date_verified": verified,
        "cross_source_matching_permitted": verified,
        "cross_source_matches_certified": 0,
        "signals_authorized": 0,
        "block_reason": None if verified else "FLASHSCORE_DATE_NOT_VERIFIED",
    }


def main() -> None:
    sofa = json.loads(SOFA.read_text(encoding="utf-8"))
    flash = json.loads(FLASH.read_text(encoding="utf-8"))
    print(json.dumps(readiness(sofa, flash), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
