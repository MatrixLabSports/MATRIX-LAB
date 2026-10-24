from pathlib import Path

WF=Path(".github/workflows/football-daily-governed-pipeline.yml")


def test_provider_outage_is_persisted_instead_of_silently_dropped():
    t=WF.read_text(encoding="utf-8")
    assert "id: cycle" in t
    assert "PROVIDER_BLOCKED_FAIL_CLOSED" in t
    assert "MATRIX_API_FOOTBALL_PROVIDER_BLOCKER_LAST.json" in t
    assert "silent_data_loss" in t
    assert "if: steps.cycle.outputs.status == 'PASS'" in t
    assert "if: always() && steps.cycle.outputs.status != 'UNEXPECTED_FAILURE'" in t


def test_priority_market_lab_is_persisted_even_when_daily_cycle_is_blocked():
    t=WF.read_text(encoding="utf-8")
    assert "Start physically priced priority market labs" in t
    assert "priority_market_lab_last.json" in t
    assert "git add evidence/api_football/market_expansion/priority_market_lab_last.json" in t


def test_provider_failure_evidence_is_added_when_present():
    t=WF.read_text(encoding="utf-8")
    assert "if [ -d evidence/api_football/provider_failures ]; then git add evidence/api_football/provider_failures; fi" in t
