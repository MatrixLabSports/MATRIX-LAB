import json

from tools.matrix_offline_browser_coverage_audit import audit


def test_missing_files_are_unknown_not_zero(tmp_path):
    result = audit(tmp_path)
    assert result["sources"]["cdp"]["present"] is False
    assert "CDP_FILE_MISSING" in result["blockers"]
    assert result["operational_certified"] is False
    assert result["real_money"] == "BLOCKED"


def test_only_safe_aggregate_fields_are_printed(tmp_path):
    data = {"status": "PASS_ACTUATOR_RAN", "counts": {"NO_SIGNAL_ECONOMIC_GATE": 1},
            "results": [{"status": "NO_SIGNAL_ECONOMIC_GATE", "token": "DO_NOT_LEAK",
                         "fixture_id": 1490582, "odds": 1.31, "ev": -0.1469}],
            "secret": "DO_NOT_LEAK"}
    (tmp_path / "MATRIX_QUOTE_RECOVERY_ACTUATOR_LAST.json").write_text(json.dumps(data), encoding="utf-8")
    result = audit(tmp_path)
    assert result["sources"]["recovery"]["counts"] == {"NO_SIGNAL_ECONOMIC_GATE": 1}
    assert result["sources"]["recovery"]["result_status_counts"] == {"NO_SIGNAL_ECONOMIC_GATE": 1}
    assert "DO_NOT_LEAK" not in json.dumps(result)
    assert result["telegram_delivery_certified"] is False


def test_malformed_json_is_blocked(tmp_path):
    (tmp_path / "MATRIX_BROWSER_CDP_COLLECTION_LAST.json").write_text("{", encoding="utf-8")
    result = audit(tmp_path)
    assert "CDP_PARSE_FAILED" in result["blockers"]
