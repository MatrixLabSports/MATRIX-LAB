"""Synthetic adversarial checks for exact-identity 13-lane frozen-cohort measurement."""
from copy import deepcopy

import pytest

from tools.matrix_13_market_exact_cohort_calibration import (
    REGISTRY, _prediction_and_targets, build, digest, statistics,
)
import json


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def freeze(lane, prediction, *, start="2026-10-25T20:00:00+00:00",
           frozen="2026-10-25T19:00:00+00:00"):
    return {
        "market_lane":lane,"fixture_id":"real-id-1","event_id":"real-id-1",
        "record_type":"PROSPECTIVE_PREMATCH_FREEZE","prospective_admitted":True,
        "freeze_timestamp_utc":frozen,"event_start_utc":start,
        "prediction_snapshot_sha256":"a"*64,"prediction":prediction,
        "real_money":"BLOCKED","automatic_wagering":False,
        "odds_used_to_generate_probability":False,"target_outcome":None,
        "settlement":None,
    }


def result():
    return {
        "fixture_id":"real-id-1","terminal_status":"FT",
        "kickoff_utc":"2026-10-25T20:00:00+00:00",
        "freeze_at_utc":"2026-10-25T19:00:00+00:00",
        "settled_at_utc":"2026-10-25T22:00:00+00:00",
        "fulltime_home_goals":2,"fulltime_away_goals":1,
        "result_source_provider":"api_football",
        "result_payload_sha256":"b"*64,
        "real_money":"BLOCKED",
    }


def test_exact_home_goals_and_one_x_two_calibrated_without_promoting():
    items = [
        freeze("TEAM_TOTAL_GOALS_HOME",{"over_0_5":0.9,"over_1_5":0.7,"over_2_5":0.3}),
        freeze("MATCH_RESULT_1X2",{"H":0.7,"D":0.2,"A":0.1}),
        freeze("TOTAL_GOALS_OVER_UNDER",{"over_2_5":0.6,"under_2_5":0.4}),
        freeze("FIRST_HALF_TOTAL_GOALS_OVER_UNDER",{"over_0_5":0.7}),
    ]
    report = build(registry(),items,[result()])
    rows = {v["market_key"]:v for v in report["lanes"]}
    h = rows["TEAM_TOTAL_GOALS_HOME"]
    assert h["exact_cohort_final_verified"] == 1
    assert h["calibration_metrics_unpromoted"]["over_0_5"]["observed_positive_rate"] == 1
    assert h["calibration_metrics_unpromoted"]["over_1_5"]["observed_positive_rate"] == 1
    assert h["calibration_metrics_unpromoted"]["over_2_5"]["observed_positive_rate"] == 0
    assert h["decision"] == "HOLD_FT_COHORT_BELOW_600"
    assert rows["MATCH_RESULT_1X2"]["calibration_metrics_unpromoted"]["1x2"]["n"] == 1
    assert rows["TOTAL_GOALS_OVER_UNDER"]["calibration_metrics_unpromoted"]["over_2_5"]["observed_positive_rate"] == 1
    half = rows["FIRST_HALF_TOTAL_GOALS_OVER_UNDER"]
    assert half["exact_cohort_final_verified"] == 0
    assert half["blockers"]["NO_VERIFIED_HALF_TIME_GOALS_IN_SETTLEMENT_SCHEMA"] == 1
    assert not any(x["telegram_authorized_by_audit"] for x in report["lanes"])
    assert report["safety"]["real_money"] == "BLOCKED"


def test_late_and_tampered_freezes_do_not_score():
    rows = [
        freeze("TEAM_TOTAL_GOALS_AWAY",{"over_0_5":0.6,"over_1_5":0.3,"over_2_5":0.1},
               frozen="2026-10-25T20:00:00+00:00"),
        freeze("DOUBLE_CHANCE_1X",{"1X":0.8}),
    ]
    rows[1]["target_outcome"] = "H"
    r = build(registry(), rows, [result()])
    assert r["summary"]["invalid_freezes"]["INVALID_PROSPECTIVE_FREEZE"] == 2
    assert all(x["exact_cohort_final_verified"] == 0 for x in r["lanes"])


def test_mismatched_fixture_start_or_frozen_time_must_not_join():
    row = freeze("TEAM_TOTAL_GOALS_HOME",{"over_0_5":0.8,"over_1_5":0.7,"over_2_5":0.1})
    bad = deepcopy(result())
    bad["freeze_at_utc"] = "2026-10-25T18:00:00+00:00"
    r = build(registry(),[row],[bad])
    lane = next(x for x in r["lanes"] if x["market_key"] == "TEAM_TOTAL_GOALS_HOME")
    assert lane["exact_cohort_final_verified"] == 0
    assert lane["blockers"]["RESULT_OR_PREDICTION_IDENTITY_REJECTED"] == 1


def test_duplicate_fixture_freezes_are_quarantined():
    row = freeze("DOUBLE_CHANCE_X2",{"X2":0.7})
    r = build(registry(),[row,deepcopy(row)],[result()])
    lane = next(x for x in r["lanes"] if x["market_key"] == "DOUBLE_CHANCE_X2")
    assert lane["exact_cohort_final_verified"] == 0
    assert lane["blockers"]["DUPLICATE_FIXTURE_FREEZE"] == 2


def test_non_standard_final_and_invalid_goals_never_pass():
    with pytest.raises(ValueError,match="UNVERIFIED_SETTLEMENT_SOURCE"):
        build(registry(),[],[{**result(),"terminal_status":"AET"}])
    bad = {**result(),"fulltime_home_goals":True}
    r = build(registry(),[freeze("TEAM_TOTAL_GOALS_HOME",{"over_0_5":.8,"over_1_5":.7,"over_2_5":.3})],[bad])
    lane = next(x for x in r["lanes"] if x["market_key"] == "TEAM_TOTAL_GOALS_HOME")
    assert lane["exact_cohort_final_verified"] == 0


def test_metric_quality_control():
    with pytest.raises(ValueError,match="PROBABILITY_OUTSIDE_0_1"):
        statistics([float("nan")],[1])
    with pytest.raises(ValueError,match="NOT_NORMALIZED"):
        statistics([{"H":0.5,"D":0.5,"A":0.5}],["H"],multiclass=True)
    assert statistics([0.5,0.5],[1,0])["brier"] == .25


def test_no_old_observations_counted_without_exact_settlements():
    r = build(registry(),[],[])
    assert r["summary"]["markets_targeted"] == 13
    assert r["summary"]["market_count_with_any_exact_final"] == 0
    assert r["summary"]["markets_with_600_exact_final"] == 0
    assert len(r["lanes"]) == 13
    assert all(not x["parameters_refitted"] for x in r["lanes"])
