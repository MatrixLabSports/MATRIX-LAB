from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path("tools/api_football_market_calibration_v2_sync.py")
SPEC = importlib.util.spec_from_file_location("market_v2", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def _row(freeze: str, *, mutated: bool = False, tuned: bool = False):
    return {
        "fixture_id": "999001",
        "freeze_at_utc": freeze,
        "kickoff_utc": "2026-10-05T20:00:00+00:00",
        "settled_at_utc": "2026-10-05T22:00:00+00:00",
        "frozen_challenger_probabilities": {
            "1x2": {"H": 0.50, "D": 0.30, "A": 0.20},
            "over_2_5": 0.60,
            "btts_v2": 0.70,
        },
        "outcomes": {"1x2": "D", "over_2_5": True, "btts": True},
        "record_sha256": "source-record-sha",
        "target_key": "api_football:fixture:999001",
        "parameters_mutated_after_freeze": mutated,
        "used_for_parameter_tuning": tuned,
    }


def test_pre_v2_rows_are_never_carried_forward():
    lanes = MOD.build_lane_records([_row("2026-10-04T18:51:31Z")])
    assert set(lanes) == {
        "1x2", "over_2_5", "under_2_5", "double_chance_1x", "double_chance_x2"
    }
    assert all(rows == [] for rows in lanes.values())


def test_each_active_market_has_separate_observation():
    lanes = MOD.build_lane_records([_row("2026-10-04T18:51:32Z")])
    assert all(len(rows) == 1 for rows in lanes.values())
    assert lanes["1x2"][0]["market"] == "1X2"
    assert lanes["over_2_5"][0]["market"] == "OVER_2_5"
    assert lanes["under_2_5"][0]["market"] == "UNDER_2_5"
    assert lanes["double_chance_1x"][0]["market"] == "DOUBLE_CHANCE_1X"
    assert lanes["double_chance_x2"][0]["market"] == "DOUBLE_CHANCE_X2"


def test_derived_markets_only_use_parent_frozen_probability():
    lanes = MOD.build_lane_records([_row("2026-10-04T19:00:00Z")])
    assert lanes["under_2_5"][0]["frozen_probability"] == pytest.approx(0.40)
    assert lanes["under_2_5"][0]["outcome"] is False
    assert lanes["under_2_5"][0]["parent_market"] == "OVER_2_5"

    assert lanes["double_chance_1x"][0]["frozen_probability"] == pytest.approx(0.80)
    assert lanes["double_chance_1x"][0]["outcome"] is True
    assert lanes["double_chance_1x"][0]["parent_market"] == "1X2"

    assert lanes["double_chance_x2"][0]["frozen_probability"] == pytest.approx(0.50)
    assert lanes["double_chance_x2"][0]["outcome"] is True
    assert lanes["double_chance_x2"][0]["parent_market"] == "1X2"


def test_btts_and_blocked_markets_are_not_silently_mixed_into_v2():
    lanes = MOD.build_lane_records([_row("2026-10-04T19:00:00Z")])
    assert "btts" not in lanes
    assert "corners_over_under" not in lanes
    assert "player_shots" not in lanes
    serialized = str(lanes)
    assert "btts_v2" not in serialized


def test_mutated_or_tuned_source_row_is_rejected():
    with pytest.raises(RuntimeError, match="PARAMETER_MUTATION_SOURCE_ROW"):
        MOD.build_lane_records([_row("2026-10-04T19:00:00Z", mutated=True)])
    with pytest.raises(RuntimeError, match="TUNING_SOURCE_ROW"):
        MOD.build_lane_records([_row("2026-10-04T19:00:00Z", tuned=True)])


def test_non_prematch_source_freeze_is_rejected():
    row = _row("2026-10-05T20:00:00Z")
    with pytest.raises(RuntimeError, match="NON_PREMATCH_SOURCE_FREEZE"):
        MOD.build_lane_records([row])
