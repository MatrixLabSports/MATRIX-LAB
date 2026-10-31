import json
from pathlib import Path

from tools.rapidapi_tennis_live_shadow import run


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}
    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return FakeResponse(
            self.payloads.pop(0),
            headers={"x-ratelimit-requests-remaining": "1150000"}
        )


def _payload():
    return {
        "success": True,
        "results": [{
            "id": "777",
            "matchId": "1-2-3-4",
            "status": "InPlay",
            "score": "6-4,2-1",
            "points": "30-15",
            "indicator": "1,0",
            "tourType": "atp",
            "participant1": "Player A",
            "participant2": "Player B",
            "league": "Cali Challenger",
            "tournament": {
                "id": 3,
                "name": "Cali",
                "level": "Challenger",
                "surface": "Clay",
                "country": "COL"
            }
        }]
    }


def test_shadow_detects_quality_valid_challenger_clay(tmp_path: Path):
    out = tmp_path / "shadow.json"
    s = FakeSession([_payload()])
    result = run(key="secret", cycles=1, interval_seconds=1, out=out, session=s)
    assert result["network_calls"] == 1
    assert result["challenger_men_clay_candidate_rows"] == 1
    assert result["quality_valid_shadow_candidate_rows"] == 1
    assert result["candidate_event_ids"] == ["777"]
    assert result["calibration_admission"]["admitted_to_existing_live_gate"] is False
    assert result["protections"]["api_tennis_retired_source_used"] is False
    assert result["protections"]["real_money"] == "BLOCKED"


def test_shadow_rejects_non_challenger_or_missing_live_quality(tmp_path: Path):
    p = _payload()
    p["results"][0]["tournament"]["level"] = "ATP"
    p["results"][0]["points"] = None
    out = tmp_path / "shadow.json"
    result = run(
        key="secret",
        cycles=1,
        interval_seconds=1,
        out=out,
        session=FakeSession([p]),
    )
    assert result["challenger_men_clay_candidate_rows"] == 0
    assert result["quality_valid_shadow_candidate_rows"] == 0
