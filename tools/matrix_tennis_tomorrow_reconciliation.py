"""Compare saved SofaScore 31-Oct with Flashscore 'mañana' capture.

Review-only. No fixture certification, quote lookup or Telegram dispatch.
"""
from __future__ import annotations
import json
from pathlib import Path
from tools.matrix_tennis_cross_source_candidates import reconcile
from tools.matrix_tennis_calendar_reconciliation_gate import SOFA

FLASH_TOMORROW = Path(__file__).resolve().parents[1] / "evidence/calendar/MATRIX_FLASHSCORE_TENNIS_MANANA_20261031_DISCOVERY.json"

def compare(sofa: dict, tomorrow: dict, target_date: str) -> dict:
    if tomorrow.get("source") != "FLASHSCORE":
        raise ValueError("Unexpected source")
    if tomorrow.get("source_page") != "https://www.flashscore.co/tenis/manana/":
        raise ValueError("Not Flashscore tomorrow calendar")
    if tomorrow.get("user_supplied_calendar_date") != target_date:
        raise ValueError("Calendar date mismatch")
    if tomorrow.get("individual_event_dates_verified") is not False:
        raise ValueError("Unexpected event date certification")
    result = reconcile(sofa, tomorrow, target_date)
    result["flashscore_source_page"] = tomorrow["source_page"]
    result["capture_date_context_accepted"] = True
    result["individual_event_dates_verified"] = False
    result["matches_certified"] = 0
    result["signals_authorized"] = 0
    return result

def main() -> None:
    sofa = json.loads(SOFA.read_text(encoding="utf-8"))
    flash = json.loads(FLASH_TOMORROW.read_text(encoding="utf-8"))
    result = compare(sofa, flash, "2026-10-31")
    print(json.dumps({k:v for k,v in result.items() if k!="candidates"}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
