"""Synthetic-only gate integrity regression, never sports outcome evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from tools.matrix_42_market_integrity_audit import audit


def fixtures():
    ids = [("F%02d" % i, "football") for i in range(30)] + [
        ("T%02d" % i, "tennis") for i in range(12)]
    counts = [727]*5 + [634]*6 + [627]*2 + [3]*2 + [0]*15 + [99] + [0]*11
    assert len(counts) == 42
    reg_lanes = {}
    sup_rows = []
    zero_rows = []
    for (k, sport), n in zip(ids, counts):
        reg_lanes[k] = {
            "display_name": k, "sport": sport, "prospective_unique_count": n,
            "gates": {"600": {"count": min(n, 600)}},
            "production_authorized_by_registry": False,
        }
        sup_rows.append({
            "market_key": k, "sport": sport, "display_name": k,
            "operational_state": "LAB", "production_authorized": False,
        })
        if n == 0:
            zero_rows.append({"market_lane": k, "blocker": "MISSING_SOURCE"})
    reg = {
        "generated_at_utc": "2026-11-18T10:13:42Z",
        "lanes": reg_lanes,
        "counts": {"ledger_rows_total": sum(counts),
                   "lanes_at_600": 13,
                   "lanes_with_any_valid_prospective": 16},
        "source_inventory": {
            "football": {"source_path": "legacy.json",
                         "source_usable_for_new_freeze_now": False,
                         "blocker": "STALE"},
            "tennis": {"today": {"available": False},
                       "tomorrow": {"available": False}},
        },
    }
    sup = {"rows": sup_rows}
    board = {"generated_at_utc": "2026-10-25T05:28:57Z",
             "counts": {"lanes_at_600": 5}}
    zero = {"rows": zero_rows, "zero_prospective_lane_count": 26}
    gate = {"generated_at_utc": "2026-10-25T05:28:57Z",
            "audit_overall_verdict": "HOLD",
            "lanes": [{"market_lane": "F00", "exact_settled_count": 42,
                       "verdict": "HOLD"}]}
    return reg, sup, board, zero, gate


def test_42_market_gate_is_read_only_and_no_600_means_promotion():
    result = audit(*fixtures())
    counts = result["market_counts"]
    assert counts == {
        "all": 42, "football": 30, "tennis": 12, "with_prospective": 16,
        "zero_prospective": 26, "at_600_freezes": 13,
        "market_lane_observation_rows": 8798,
    }
    assert result["latest_available_gate600_settlement_audit"]["verdict"] == "HOLD"
    assert result["dated_difference"]["old_board_market_lanes_at_600"] == 5
    assert result["dated_difference"]["latest_registry_market_lanes_at_600"] == 13
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"] == "BLOCKED"
    assert all(not x["calibration_pass_verified_by_this_audit"]
               for x in result["markets"])


def test_uncapped_raw_count_is_not_same_as_gate_counter():
    reg, sup, board, zero, gate = fixtures()
    reg["lanes"]["F00"]["gates"]["600"]["count"] = 727
    with pytest.raises(ValueError, match="MARKET_COUNT_GATE_DIVERGENCE"):
        audit(reg, sup, board, zero, gate)


def test_duplicate_supervisor_market_fails():
    reg, sup, board, zero, gate = fixtures()
    sup["rows"][0] = dict(sup["rows"][1])
    with pytest.raises(ValueError, match="MARKET_REGISTRY_SUPERVISOR_KEY_CONFLICT"):
        audit(reg, sup, board, zero, gate)


def test_missing_zero_market_reason_is_not_silently_dropped():
    reg, sup, board, zero, gate = fixtures()
    zero["rows"].pop()
    with pytest.raises(ValueError, match="MARKET_MISSING_ZERO_BLOCKER"):
        audit(reg, sup, board, zero, gate)


def test_false_stale_board_treated_as_newer_is_rejected():
    reg, sup, board, zero, gate = fixtures()
    board["generated_at_utc"] = "2026-11-19T00:00:00Z"
    with pytest.raises(ValueError, match="MARKET_BOARD_NEWER_THAN_REGISTRY"):
        audit(reg, sup, board, zero, gate)


def test_count_inflation_not_allowed():
    reg, sup, board, zero, gate = fixtures()
    reg["lanes"]["F00"]["prospective_unique_count"] += 1
    with pytest.raises(ValueError, match="MARKET_COUNTER_TOTALS_NOT_RECONCILED"):
        audit(reg, sup, board, zero, gate)


def test_production_claims_are_only_diagnostic_not_authorization():
    reg, sup, board, zero, gate = fixtures()
    sup["rows"][0]["production_authorized"] = True
    report = audit(reg, sup, board, zero, gate)
    assert "F00" in report["production_claims_require_separate_adjudication"]
    assert report["telegram_signal_authorized"] is False
    assert not any(x["production_signal_authorized_by_this_audit"]
                   for x in report["markets"])
