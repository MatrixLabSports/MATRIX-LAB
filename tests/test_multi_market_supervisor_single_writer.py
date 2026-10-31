from pathlib import Path

FOOTBALL = Path(".github/workflows/football-daily-governed-pipeline.yml")
TENNIS = Path(".github/workflows/rapidapi-tennis-paid-window-harvest.yml")
CANONICAL = Path(".github/workflows/matrix-multi-market-supervisor.yml")


def test_each_source_has_its_own_supervisor_evidence_file():
    football=FOOTBALL.read_text(encoding="utf-8")
    tennis=TENNIS.read_text(encoding="utf-8")
    assert "MATRIX_MULTI_MARKET_SUPERVISOR_FOOTBALL_LAST.json" in football
    assert "MATRIX_MULTI_MARKET_SUPERVISOR_TENNIS_LAST.json" not in football
    assert "MATRIX_MULTI_MARKET_SUPERVISOR_TENNIS_LAST.json" in tennis
    assert "MATRIX_MULTI_MARKET_SUPERVISOR_FOOTBALL_LAST.json" not in tennis


def test_only_canonical_workflow_writes_canonical_last():
    football=FOOTBALL.read_text(encoding="utf-8")
    tennis=TENNIS.read_text(encoding="utf-8")
    canonical=CANONICAL.read_text(encoding="utf-8")
    canonical_path="evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"
    assert canonical_path not in football
    assert canonical_path not in tennis
    assert canonical_path in canonical
    assert "group: matrix-multi-market-canonical-supervisor" in canonical
    assert "cancel-in-progress: false" in canonical


def test_canonical_supervisor_is_triggered_after_both_paid_cycles():
    canonical=CANONICAL.read_text(encoding="utf-8")
    assert '"MATRIX Football Daily Governed Pipeline"' in canonical
    assert '"MATRIX RapidAPI Tennis Paid-Window Harvest"' in canonical
