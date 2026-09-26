import json
from pathlib import Path

from tools.cor0203_source_readiness import classify_source_readiness, persist_transition


def test_missing_api_key_is_not_no_events():
    report = classify_source_readiness({
        "provider": "api_tennis",
        "status": "API_TENNIS_KEY_NOT_CONFIGURED",
        "network_calls": 0,
    })
    assert report["ready"] is False
    assert report["cause"] == "PROVIDER_CREDENTIAL_NOT_CONFIGURED"
    assert report["production_discovery_ready"] is False


def test_completed_discovery_requires_real_network_call():
    report = classify_source_readiness({
        "provider": "api_tennis",
        "status": "DISCOVERY_COMPLETED",
        "network_calls": 3,
    })
    assert report["ready"] is True
    assert report["cause"] == "READY"


def test_status_transition_is_append_only_and_deduplicated(tmp_path):
    report = classify_source_readiness({
        "provider": "api_tennis",
        "status": "API_TENNIS_KEY_NOT_CONFIGURED",
        "network_calls": 0,
    })
    first, created_first = persist_transition(report=report, evidence_dir=tmp_path)
    second, created_second = persist_transition(report=report, evidence_dir=tmp_path)
    assert first == second
    assert created_first is True
    assert created_second is False
    assert json.loads(first.read_text())["ready"] is False
