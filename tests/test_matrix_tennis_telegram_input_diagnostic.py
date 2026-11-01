import json
from pathlib import Path
from tools.matrix_tennis_telegram_input_diagnostic import inspect


def test_missing_date_reports_missing(tmp_path):
    result = inspect(tmp_path, "2026-11-01")
    assert result["status"] == "NO_CANONICAL_TENNIS_INPUT"
    assert result["rows_total"] == 0


def test_counts_governance_and_verified_quotes(tmp_path):
    folder = tmp_path / "2026-11-01"
    folder.mkdir()
    rows = [
        {"governance_status": "PROMOTED", "physical_quote_verified": True,
         "p_matrix": .65, "decimal_odds": 1.8, "ev": .17},
        {"governance_status": "RESEARCH", "physical_quote_verified": True,
         "p_matrix": .8, "decimal_odds": 2.0, "ev": .6},
        {"governance_status": "PROMOTED", "physical_quote_verified": False,
         "p_matrix": .8, "decimal_odds": 2.0, "ev": .6},
    ]
    (folder / "a.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    result = inspect(tmp_path, "2026-11-01")
    assert result["rows_total"] == 3
    assert result["rows_governed"] == 2
    assert result["rows_with_physical_quote"] == 1
    assert result["rows_positive_ev_and_odds_gt_1_50"] == 1


def test_malformed_file_is_ignored(tmp_path):
    folder = tmp_path / "2026-11-01"
    folder.mkdir()
    (folder / "broken.json").write_text("{bad", encoding="utf-8")
    result = inspect(tmp_path, "2026-11-01")
    assert result["json_files"] == 1
    assert result["rows_total"] == 0
