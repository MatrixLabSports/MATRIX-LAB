from __future__ import annotations

from copy import deepcopy

from tools.cor0203_batch_preflight import partition_batch


HOLDOUT = "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
FREEZE = "2026-09-25T12:00:00+00:00"


def _player(name: str, source_id: str, rank: int) -> dict:
    return {
        "name": name,
        "source_id": source_id,
        "hand": "R",
        "age": 24.0,
        "rank": rank,
        "rank_points": 300,
    }


def _state() -> dict:
    players = ["Player A", "Player B", "Player C", "Player D"]
    return {
        "history": {
            "matches": {p: [1, 0, 1, 1, 0] for p in players},
            "overall": {p: [3.0, 5.0] for p in players},
            "surface": {p: {"Hard": [3.0, 5.0]} for p in players},
            "serve": {p: [150.0, 250.0] for p in players},
            "ret": {p: [100.0, 250.0] for p in players},
            "opp_strength": {p: [2.5, 5.0] for p in players},
        },
        "elo_overall": {p: 1500.0 for p in players},
        "elo_surface": {"Hard": {p: 1500.0 for p in players}},
        "glicko_overall": {p: {"r": 1500.0, "rd": 100.0} for p in players},
        "glicko_surface": {"Hard": {p: {"r": 1500.0, "rd": 100.0} for p in players}},
    }


def _prefeature() -> dict:
    return {
        "holdout_id": HOLDOUT,
        "created_before_feature_acquisition": True,
        "starting_observation_count": 9,
        "events": [
            {
                "event_id": "e10",
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            },
            {
                "event_id": "e11",
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            },
        ],
    }


def _events() -> dict:
    return {
        "holdout_id": HOLDOUT,
        "starting_observation_count": 9,
        "control_probability_window1": 0.4967,
        "events": [
            {
                "event_id": "e10",
                "surface": "Hard",
                "tour_level": "C",
                "target_period": 20260921,
                "event_start_utc": "2026-09-26T14:00:00+00:00",
                "players": [_player("Player A", "A1", 100), _player("Player B", "B1", 120)],
            },
            {
                "event_id": "e11",
                "surface": "Hard",
                "tour_level": "ATP Challenger",
                "target_period": 20260921,
                "event_start_utc": "2026-09-26T16:00:00+00:00",
                "players": [_player("Player C", "C1", 140), _player("Player D", "D1", 160)],
            },
        ],
    }


def _static4() -> dict:
    return {
        "holdout_id": HOLDOUT,
        "events": [
            {
                "event_id": "e10",
                "players": {
                    "Player A": {"source_id": "A1", "hand": "R", "age": 24.0, "rank": 100, "rank_points": 300},
                    "Player B": {"source_id": "B1", "hand": "R", "age": 24.0, "rank": 120, "rank_points": 300},
                },
            },
            {
                "event_id": "e11",
                "players": {
                    "Player C": {"source_id": "C1", "hand": "R", "age": 24.0, "rank": 140, "rank_points": 300},
                    "Player D": {"source_id": "D1", "hand": "R", "age": 24.0, "rank": 160, "rank_points": 300},
                },
            },
        ],
    }


def test_partition_keeps_valid_event_when_other_event_has_missing_history():
    state = _state()
    state["history"]["serve"]["Player D"] = [0.0, 0.0]

    result = partition_batch(
        prefeature=_prefeature(),
        static4=_static4(),
        events=_events(),
        state=state,
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    assert result["input_events"] == 2
    assert result["valid_events"] == 1
    assert result["blocked_events"] == 1
    assert result["valid_event_ids"] == ["e10"]
    assert result["filtered_manifest"]["events"][0]["event_id"] == "e10"
    assert result["result"] == "PASS_WITH_BLOCKERS"
    assert "SERVE_HISTORY_MISSING:Player D" in result["blocked"][0]["blockers"]


def test_static4_value_mismatch_blocks_only_affected_event():
    static4 = _static4()
    static4["events"][0]["players"]["Player A"]["rank"] = 999

    result = partition_batch(
        prefeature=_prefeature(),
        static4=static4,
        events=_events(),
        state=_state(),
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    assert result["valid_event_ids"] == ["e11"]
    first = next(row for row in result["blocked"] if row["event_id"] == "e10")
    assert "STATIC4_VALUE_MISMATCH:Player A:rank" in first["blockers"]


def test_missing_surface_rating_is_explicit_blocker_not_1500_fallback():
    state = _state()
    del state["elo_surface"]["Hard"]["Player B"]

    result = partition_batch(
        prefeature=_prefeature(),
        static4=_static4(),
        events=_events(),
        state=state,
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    first = next(row for row in result["blocked"] if row["event_id"] == "e10")
    assert "ELO_SURFACE_MISSING:Player B" in first["blockers"]
    assert result["valid_event_ids"] == ["e11"]


def test_all_blocked_is_a_persistable_result_not_a_batch_exception():
    state = _state()
    state["history"]["matches"] = {}

    result = partition_batch(
        prefeature=_prefeature(),
        static4=_static4(),
        events=_events(),
        state=state,
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    assert result["valid_events"] == 0
    assert result["blocked_events"] == 2
    assert result["result"] == "ALL_BLOCKED"
    assert result["filtered_manifest"]["events"] == []


def test_single_event_legacy_static4_shape_is_supported():
    events = _events()
    events["events"] = [events["events"][0]]
    pre = _prefeature()
    pre["events"] = [pre["events"][0]]
    static4 = {
        "holdout_id": HOLDOUT,
        "event_id": "e10",
        "players": _static4()["events"][0]["players"],
    }

    result = partition_batch(
        prefeature=pre,
        static4=static4,
        events=events,
        state=_state(),
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    assert result["result"] == "PASS"
    assert result["valid_event_ids"] == ["e10"]


def test_post_start_event_is_blocked_without_poisoning_other_event():
    events = _events()
    events["events"][0]["event_start_utc"] = "2026-09-25T11:00:00+00:00"

    result = partition_batch(
        prefeature=_prefeature(),
        static4=_static4(),
        events=events,
        state=_state(),
        freeze_at_utc=FREEZE,
        expected_starting_count=9,
    )

    assert result["valid_event_ids"] == ["e11"]
    first = next(row for row in result["blocked"] if row["event_id"] == "e10")
    assert "POST_START_FREEZE_FORBIDDEN" in first["blockers"]
