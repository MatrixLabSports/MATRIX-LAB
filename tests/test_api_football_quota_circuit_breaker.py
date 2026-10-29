"""Daily API-Football quota circuit-breaker regression test."""
import json
from datetime import datetime, timezone
from tests.test_api_football_prospective_api_settlement import FakeSession, _write_freeze
from tools.api_football_prospective_api_settlement import run


def test_quota_exhaustion_stops_calls_and_preserves_ledger(tmp_path):
    _write_freeze(tmp_path)
    freeze_path = tmp_path / "prospective_market_freeze" / "freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    second = dict(freeze["rows"][0])
    second["fixture_id"] = "901"
    second["target_key"] = "api_football:fixture:901"
    freeze["rows"].append(second)
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    payload = {"errors": {"requests": "You have reached the request limit for the day"}, "response": []}
    session = FakeSession(payload)
    result = run(tmp_path, "test-key", datetime(2026, 9, 28, 20, 1, tzinfo=timezone.utc), session)
    assert result["quota_exhausted"] is True
    assert result["network_calls"] == len(session.calls) == 1
    assert result["new_settlement_count"] == 0
    assert [row["reason"] for row in result["blocked"]] == [
        "API_FOOTBALL_DAILY_QUOTA_EXHAUSTED",
        "API_FOOTBALL_DAILY_QUOTA_EXHAUSTED_DEFERRED",
    ]
    assert result["real_money"] == "BLOCKED"
    assert not (tmp_path / "prospective_market_freeze" / "settlement_ledger.jsonl").exists()
