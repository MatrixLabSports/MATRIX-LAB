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
    assert result["signals_sent"] is None
    assert result["telegram_delivery_checked"] is False
    assert result["root_cause_confirmed"] is False
    assert result["missing_canonical_sources"] == ["tennis_canonical", "football_canonical"]


def test_invalid_date_fails_closed(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="DATE_FORMAT"):
        audit("../wrong", browser=tmp_path, football=tmp_path, tennis=tmp_path)


def test_impossible_calendar_date_fails_closed(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="DATE_FORMAT"):
        audit("2026-02-30", browser=tmp_path, football=tmp_path, tennis=tmp_path)
