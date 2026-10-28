from tools.telegram_opera_bookmaker_coverage_contract import EXPECTED, validate

def test_expected_colombia_execution_portfolio_is_14():
    assert len(EXPECTED) == 14
    assert len(set(EXPECTED)) == 14

def test_current_opera_coverage_manifest_is_consistent():
    data=validate()
    assert data["summary"]["configured_execution_houses"] == 14
    assert data["summary"]["opera_open_observed"] == 7
    assert data["summary"]["opera_not_observed_open"] == 7
    assert data["interpretation"]["no_app_installation_required"] is True
    assert data["governance"]["real_money"] == "BLOCKED"
