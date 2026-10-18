import json
from pathlib import Path
from unittest.mock import Mock

from tools.api_football_bookmaker_catalog_probe import run


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7400",
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "299",
        }
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


def test_catalog_detects_pinnacle_and_persists_sha(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "errors": {},
        "response": [
            {"id": 1, "name": "Bet365"},
            {"id": 2, "name": "Pinnacle"},
        ],
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "PASS"
    assert result["network_calls_performed"] == 1
    assert result["provider_rows"] == 2
    assert result["pinnacle_found"] is True
    assert result["pinnacle_matches"] == [{"id": 2, "name": "Pinnacle"}]
    assert result["real_money"] == "BLOCKED"
    assert (tmp_path / "bookmakers.bin").is_file()
    assert len(result["raw_sha256"]) == 64


def test_catalog_passes_without_pinnacle_but_reports_false(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "errors": {},
        "response": [{"id": 1, "name": "Bet365"}],
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "PASS"
    assert result["pinnacle_found"] is False


def test_provider_error_blocks(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "errors": {"access": "blocked"},
        "response": [],
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "BLOCKED"
    assert result["provider_error"] is True
