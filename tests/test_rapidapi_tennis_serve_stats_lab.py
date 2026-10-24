import json
from pathlib import Path

from tools.rapidapi_tennis_serve_stats_lab import _extract_stats, _timeline_break_count, run


class Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class Session:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if url.endswith("/tennis/v2/extend/api/events/live"):
            return Resp({
                "success": True,
                "results": [{
                    "id": "123",
                    "participant1": "Player One",
                    "participant2": "Player Two",
                    "tourType": "atp",
                    "status": "InPlay",
                }],
            })
        if "/event/data/statistics/" in url:
            return Resp({
                "success": True,
                "statistics": {
                    "ALL": {
                        "service": {
                            "aces": {
                                "player1": {"value": 7},
                                "player2": {"value": 4},
                            },
                            "doubleFaults": {
                                "player1": {"value": 2},
                                "player2": {"value": 3},
                            },
                        },
                        "return": {
                            "breakPointsScored": {
                                "player1": {"value": 3},
                                "player2": {"value": 1},
                            },
                        },
                    },
                },
            })
        if "/event/timeline/123" in url:
            return Resp({
                "success": True,
                "results": [
                    {"id": "a", "text": "Game 3 - Player One - breaks to 30"},
                    {"id": "b", "text": "Game 4 - Player Two - holds to 15"},
                    {"id": "c", "text": "Game 8 - Player Two - breaks to love"},
                ],
            })
        raise AssertionError(url)


def test_extract_stats_maps_three_required_stat_families():
    payload = {
        "statistics": {
            "ALL": {
                "service": {
                    "aces": {"player1": {"value": 6}, "player2": {"value": 3}},
                    "doubleFaults": {"player1": {"value": 1}, "player2": {"value": 2}},
                },
                "return": {
                    "breakPointsScored": {"player1": {"value": 2}, "player2": {"value": 1}},
                },
            }
        }
    }
    out = _extract_stats(payload)
    assert out["aces"] == {"player1": 6.0, "player2": 3.0}
    assert out["double_faults"] == {"player1": 1.0, "player2": 2.0}
    assert out["breaks_of_serve"] == {"player1": 2.0, "player2": 1.0}


def test_timeline_break_crosscheck_counts_only_break_events():
    assert _timeline_break_count({
        "results": [
            {"text": "Game 1 - A - breaks to 30"},
            {"text": "Game 2 - B - holds"},
            {"text": "Game 3 - B - breaks to love"},
        ]
    }) == 2


def test_source_lab_observes_all_three_market_families_without_generating_probability(tmp_path: Path):
    out_path = tmp_path / "serve_stats.json"
    result = run(
        key="secret",
        out=out_path,
        max_events=4,
        session=Session(),
    )
    assert result["status"] == "PASS_SOURCE_LAB"
    assert result["field_observation_counts"] == {
        "ACES": 1,
        "DOUBLE_FAULTS": 1,
        "BREAKS_OF_SERVE": 1,
    }
    assert result["events_probed"] == 1
    assert result["network_calls"] == 3
    assert result["p_matrix_status"] == "NOT_GENERATED_SOURCE_LAB_ONLY"
    assert result["protections"]["missing_not_zero"] is True
    assert result["protections"]["silent_imputation"] is False
    assert result["protections"]["odds_used_to_generate_probability"] is False
    assert result["protections"]["automatic_wagering"] is False
    assert result["protections"]["real_money"] == "BLOCKED"
    assert out_path.exists()
