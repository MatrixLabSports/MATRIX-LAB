"""Tests for read-only adapter source locator."""
from tools.matrix_bookmaker_adapter_source_locator import locate


def test_locator_reports_only_path_line_and_known_token(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "adapter.py").write_text(
        'SECRET = "DO_NOT_PRINT"\n# BOOKMAKER_ADAPTER_NOT_CERTIFIED\n', encoding="utf-8"
    )
    (tools / "other.py").write_text('SECRET = "OTHER_PRIVATE"\n', encoding="utf-8")
    result = locate(tmp_path)
    assert result["source_matches"] == {
        "tools/adapter.py": [{"line": 2, "token": "BOOKMAKER_ADAPTER_NOT_CERTIFIED"}]
    }
    assert "DO_NOT_PRINT" not in str(result)
    assert "OTHER_PRIVATE" not in str(result)
    assert result["adapter_certified"] is False
    assert result["telegram_delivery_certified"] is False


def test_locator_excludes_evidence_and_unknown_directories(tmp_path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "secret.py").write_text("CERTIFIED_EXACT_OVER25", encoding="utf-8")
    assert locate(tmp_path)["source_matches"] == {}
