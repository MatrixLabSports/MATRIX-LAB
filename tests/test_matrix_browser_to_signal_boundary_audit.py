from tools.matrix_browser_to_signal_boundary_audit import audit


def test_browser_discovery_does_not_promote_to_signals(tmp_path):
    browser = tmp_path / "browser"
    browser.mkdir()
    (browser / "MATRIX_SOFASCORE_TENNIS_20261031_FULL_LINK_DISCOVERY.json").write_text("{}", encoding="utf-8")
    result = audit("2026-10-31", browser=browser, football=tmp_path / "football", tennis=tmp_path / "tennis")
    assert result["sources"]["browser_tennis_discovery"]["exists"] is True
    assert result["sources"]["tennis_canonical"]["json_count"] == 0
    assert result["sources"]["football_canonical"]["counts"]["over25_shadow_ev/*.json"] == 0
    assert result["browser_discovery_is_signal_input"] is False
    assert result["auto_promotion_authorized"] is False
    assert result["signals_sent"] == 0


def test_invalid_date_fails_closed(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="DATE_FORMAT"):
        audit("../wrong", browser=tmp_path, football=tmp_path, tennis=tmp_path)
