"""Offline candidate admission tests: malformed rows must not stop collection."""
from datetime import datetime, timedelta, timezone

from tools.matrix_selfhosted_browser_quote_collector import candidate_rows

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def row(p, kickoff):
    return {"fixture_id": "fixture", "p_matrix": p, "kickoff": kickoff, "match": "Equipo Uno vs Equipo Dos"}


def test_only_valid_future_timezone_aware_candidates():
    future = (NOW + timedelta(minutes=45)).isoformat()
    rows = [
        row(0.70, future),
        row("invalid", future),
        row(None, future),
        row(float("nan"), future),
        row(float("inf"), future),
        row(1.0, future),
        row(0.59, future),
        row(0.80, "2026-10-30T12:45:00"),
        row(0.80, NOW.isoformat()),
        row(0.80, (NOW + timedelta(hours=3)).isoformat()),
    ]
    result = candidate_rows({"records": rows}, NOW)
    assert len(result) == 1
    assert result[0]["p_matrix"] == 0.70


def test_missing_or_malformed_rows_do_not_crash():
    result = candidate_rows({"records": [None, {}, row({}, "bad"), row(0.8, "bad")]}, NOW)
    assert result == []
