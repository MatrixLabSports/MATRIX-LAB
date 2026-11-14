"""Regression tests: gate-600 freezes never become settled outcomes or picks."""
from __future__ import annotations

import copy
import pytest

from tools.matrix_13_market_gate600_committee import (
    REGISTRY, SUPERVISOR, CALIBRATION, PERIOD_LAB, SETTLEMENT_AUDIT,
    FIXED_5000, _read, build,
)


def inputs():
    return [
        _read(REGISTRY),
        _read(SUPERVISOR),
        _read(CALIBRATION),
        _read(PERIOD_LAB),
        _read(SETTLEMENT_AUDIT),
        _read(FIXED_5000),
    ]


def test_all_thirteen_600_freeze_lanes_covered_without_promotion():
    r = build(*inputs())
    assert r["summary"]["gate600_reached"] == 13
    assert len(r["lanes"]) == 13
    assert {x["market_key"] for x in r["lanes"]} == {
        "MATCH_RESULT_1X2", "DOUBLE_CHANCE_1X", "DOUBLE_CHANCE_X2",
        "DOUBLE_CHANCE_12", "TOTAL_GOALS_OVER_UNDER",
        "TEAM_TOTAL_GOALS_HOME", "TEAM_TOTAL_GOALS_AWAY",
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER", "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME", "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME", "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    }
    assert all(x["prospective_valid_freezes"] >= 600 for x in r["lanes"])
    assert all(not x["automatically_promoted"] for x in r["lanes"])
    assert all(not x["telegram_signal_authorized_by_this_audit"] for x in r["lanes"])


def test_old_settlement_snapshot_never_claimed_current_600():
    r = build(*inputs())
    assert r["summary"]["gate600_settlement_audit_is_at_least_as_recent_as_registry"] is False
    assert all(x["current_exact_settled_count_verified"] is None for x in r["lanes"])
    for row in r["lanes"]:
        if row["market_key"] in {"MATCH_RESULT_1X2", "DOUBLE_CHANCE_1X",
                                 "DOUBLE_CHANCE_X2", "DOUBLE_CHANCE_12"}:
            assert row["settlement_evidence"] == "OLDER_AUDIT_REFERENCE_ONLY"
            assert row["older_audit_exact_settled_reference"] is not None


def test_calibration_and_period_lab_are_different_cohorts():
    r = build(*inputs())
    by_key = {x["market_key"]: x for x in r["lanes"]}
    m = by_key["MATCH_RESULT_1X2"]
    assert m["historical_4000_metrics_separate_cohort"]["MATCH_RESULT_1X2"]["eligible_rows"] == 4000
    assert m["current_exact_settled_count_verified"] is None
    period = by_key["SECOND_HALF_TOTAL_GOALS_OVER_UNDER"]
    assert period["period_goals_research_metrics_separate_cohort"]["second_half_over_0_5"]["observations"] >= 1
    assert period["current_exact_settled_count_verified"] is None
    assert by_key["TEAM_TOTAL_GOALS_HOME"]["decision"] == "HOLD_NO_DEDICATED_OUTCOME_METRIC"
    assert by_key["DOUBLE_CHANCE_12"]["decision"] == "NO_GO_EXISTING_DIAGNOSTIC_CHALLENGER"


def test_blocks_unsafe_and_inconsistent_registry():
    data = inputs()
    data[0]["protections"]["real_money"] = "UNBLOCKED"
    with pytest.raises(ValueError, match="REGISTRY_REAL_MONEY_NOT_BLOCKED"):
        build(*data)
    data = inputs()
    data[0]["counts"]["lanes_at_600"] += 1
    with pytest.raises(ValueError, match="REGISTRY_GATE600_COUNT_MISMATCH"):
        build(*data)
    data = inputs()
    data[0]["lanes"]["MATCH_RESULT_1X2"]["prospective_unique_count"] += 1
    with pytest.raises(ValueError, match="REGISTRY_LEDGER_TOTAL_MISMATCH"):
        build(*data)


def test_no_period_research_promotion_and_fixed_prefix_sealed():
    data = inputs()
    data[3] = copy.deepcopy(data[3])
    data[3]["production_authorized"] = True
    with pytest.raises(ValueError, match="PERIOD_MODEL_UNEXPECTED_PRODUCTION"):
        build(*data)
    data = inputs()
    data[5]["automatic_promotion"] = True
    with pytest.raises(ValueError, match="FIXED_PREFIX_AUTOPROMOTION_GUARD_MISSING"):
        build(*data)


def test_governance_and_source_provenance_are_complete():
    r = build(*inputs())
    assert r["governance"]["real_money"] == "BLOCKED"
    assert r["governance"]["automatic_wagering"] is False
    assert r["governance"]["telegram_messages_sent"] == 0
    assert r["governance"]["no_automatic_promotion"] is True
    assert len(r["committee_roles"]) >= 6
    assert len(r["source_hashes_sha256"]) == 6
    assert all(len(h) == 64 for h in r["source_hashes_sha256"].values())
