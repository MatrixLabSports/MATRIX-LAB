"""Integration regression against the preserved real Opera/SofaScore capture.

Run: python -m pytest -v tests/test_matrix_calendar_tennis_20261031_evidence.py
"""
import json
from pathlib import Path
from tools.matrix_calendar_evidence_guard import normalize_calendar_links

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence/calendar/MATRIX_SOFASCORE_TENNIS_20261031_DISCOVERY.json"

def test_real_capture_integrity_and_safe_normalization():
    source = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert source["date_label"] == "2026-10-31"
    assert source["source"] == "SOFASCORE"
    assert source["timezone_verified"] is False
    assert source["flashscore_reconciled"] is False
    assert source["bookmaker_quotes_certified"] is False
    assert source["signals_authorized"] == 0
    assert len(source["records"]) == 190
    normalized = normalize_calendar_links(source["records"], source["date_label"])
    assert normalized["accepted"] == 190
    assert normalized["blocked"] == 1
    assert normalized["rejected"] == 0
    assert normalized["signals_authorized"] == 0
    assert all(row["eligible_for_signal"] is False for row in normalized["events"])
    assert all(row["bookmaker_quote"] is None for row in normalized["events"])
    assert all(row["timezone"] is None for row in normalized["events"])
    assert all(row["surface"] is None for row in normalized["events"])
