from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from tools.api_football_real_probe import run_probe


def _response(*, status=200, body=None, headers=None):
    response = Mock()
    response.status_code = status
    payload = body if body is not None else {
        "get": "countries",
        "parameters": [],
        "errors": [],
        "results": 2,
        "paging": {"current": 1, "total": 1},
        "response": [
            {"name": "England", "code": "GB"},
            {"name": "France", "code": "FR"},
        ],
    }
    raw = __import__("json").dumps(payload, separators=(",", ":")).encode("utf-8")
    response.content = raw
    response.json.return_value = payload
    response.headers = headers or {
        "content-type": "application/json",
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "9",
    }
    return response


def test_real_probe_persists_raw_response_and_verified_manifest(tmp_path):
    session = Mock()
    session.get.return_value = _response()

    result = run_probe(
        api_key="real-looking-test-key",
        out_dir=tmp_path,
        session=session,
        captured_at_utc="2026-09-28T04:00:00+00:00",
    )

    session.get.assert_called_once_with(
        "https://v3.football.api-sports.io/countries",
        headers={"x-apisports-key": "real-looking-test-key"},
        timeout=15.0,
    )
    assert result["status"] == "PASS"
    assert result["network_call_performed"] is True
    assert result["verified_successful_provider_response"] is True
    assert result["provider_results"] == 2
    assert result["real_money"] == "BLOCKED"
    assert (tmp_path / "response_body.bin").exists()
    assert (tmp_path / "probe_manifest.json").exists()
    request_text = (tmp_path / "request.json").read_text()
    assert "real-looking-test-key" not in request_text
    assert "REDACTED" in request_text


def test_real_probe_rejects_missing_secret_before_network(tmp_path):
    session = Mock()

    with pytest.raises(ValueError, match="API_FOOTBALL_KEY_NOT_CONFIGURED"):
        run_probe(api_key="", out_dir=tmp_path, session=session)

    session.get.assert_not_called()


def test_real_probe_rejects_non_ascii_secret_before_network(tmp_path):
    session = Mock()

    with pytest.raises(ValueError, match="API_FOOTBALL_KEY_MUST_BE_ASCII"):
        run_probe(api_key="••••", out_dir=tmp_path, session=session)

    session.get.assert_not_called()


def test_real_probe_persists_network_error_without_claiming_usage(tmp_path):
    session = Mock()
    session.get.side_effect = requests.Timeout("timeout")

    result = run_probe(
        api_key="test-key",
        out_dir=tmp_path,
        session=session,
        captured_at_utc="2026-09-28T04:00:00+00:00",
    )

    assert result["status"] == "NETWORK_ERROR"
    assert result["network_call_attempted"] is True
    assert result["network_call_performed"] is False
    assert result["verified_successful_provider_response"] is False
    assert (tmp_path / "probe_manifest.json").exists()
    assert not (tmp_path / "response_body.bin").exists()


def test_real_probe_fails_closed_on_provider_error_payload(tmp_path):
    session = Mock()
    session.get.return_value = _response(
        body={
            "get": "countries",
            "parameters": [],
            "errors": {"token": "Error/Missing application key"},
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "response": [],
        }
    )

    result = run_probe(api_key="test-key", out_dir=tmp_path, session=session)

    assert result["status"] == "PROVIDER_RESPONSE_NOT_VERIFIED"
    assert result["network_call_performed"] is True
    assert result["verified_successful_provider_response"] is False
    assert result["provider_results"] == 0
