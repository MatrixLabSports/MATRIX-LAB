"""Windows CDP startup integrity: fail closed and bounded health checks."""
from pathlib import Path

def test_browser_launcher_rejects_non_cdp_occupied_port_and_has_bounded_wait():
    path=Path(__file__).resolve().parents[1]/"tools/windows/start_matrix_browser_cdp.ps1"
    body=path.read_text(encoding="utf-8")
    assert 'MATRIX_BROWSER_PORT_OCCUPIED_BUT_CDP_UNVERIFIED' in body
    assert 'Test-MatrixCdpHealth' in body
    assert 'Invoke-RestMethod -Uri $health' in body
    assert 'Start-Sleep -Seconds 2' in body
    assert 'MATRIX_BROWSER_CDP_START_FAILED_AFTER_BOUNDED_HEALTH_PROBES' in body
    assert 'ws://127.0.0.1:$Port/' in body
    assert 'ws://localhost:$Port/' in body
    assert '--remote-debugging-address=127.0.0.1' in body
    assert 'Stop-Process' not in body
    assert 'taskkill' not in body.lower()

def test_browser_workflow_does_not_hide_missing_source_data():
    path=Path(__file__).resolve().parents[1]/".github/workflows/matrix-selfhosted-tennis-browser-free-30m.yml"
    src=path.read_text(encoding="utf-8")
    assert 'TENNIS_ZERO_AUTHENTIC_PRE_CUT_BIOGRAPHY_RESEARCH_MATCHES' in src
    assert 'tests/test_matrix_tennis_browser_cdp_contract.py' in src
    assert 'tools/windows/start_matrix_browser_cdp.ps1' in src
    assert 'TENNIS_NO_AUTHENTIC_CHALLENGER_DETAILS_ANY_DATE' in src
    assert 'REAL_MONEY: BLOCKED' in src
