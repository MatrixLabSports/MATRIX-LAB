"""Daily API-Football quota circuit-breaker regression test."""
import json
from datetime import datetime, timezone
class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def get(self, url, headers, params, timeout):
        self.calls.append((url, params))
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode("utf-8")
                self.payload = payload
            def json(self):
                return self.payload
        return Response(self.payload)


def _write_freeze(root):
    folder = root / "prospective_market_freeze"
    folder.mkdir(parents=True, exist_ok=True)
    freeze = {"rows": [{"fixture_id": "900", "target_key": "api_football:fixture:900",
        "kickoff_utc": "2026-09-28T18:00:00+00:00", "freeze_at_utc": "2026-09-28T12:00:00+00:00",
        "input_sha256": "a" * 64, "home_team_id": "40", "away_team_id": "41",
        "frozen_research_probabilities": {"over_2_5": 0.55}}]}
    (folder / "freeze.json").write_text(json.dumps(freeze), encoding="utf-8")
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


def test_quota_resets_on_new_run(tmp_path):
    """A quota failure must not persist as a permanent cross-run block."""
    _write_freeze(tmp_path)
    payload = {"errors": {"requests": "You have reached the request limit for the day"}, "response": []}
    first = FakeSession(payload)
    result1 = run(tmp_path, "test-key", datetime(2026, 9, 28, 20, 1, tzinfo=timezone.utc), first)
    assert result1["quota_exhausted"] is True
    second = FakeSession({"response": []})
    result2 = run(tmp_path, "test-key", datetime(2026, 9, 29, 20, 1, tzinfo=timezone.utc), second)
    assert result2["quota_exhausted"] is False
    assert result2["network_calls"] == len(second.calls) == 1
    assert result2["new_settlement_count"] == 0
    assert result2["real_money"] == "BLOCKED"
