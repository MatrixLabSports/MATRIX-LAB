"""Synthetic-only Bayesian shadow gates: no real fixture, odds or model updates."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from tools.matrix_hybrid_elite_bayesian_shadow import build

UTC = timezone.utc
START = datetime(2026, 11, 18, 20, tzinfo=UTC)


def docs(n=35, lane="FOOTBALL_OVER25"):
    history = {"schema": "MATRIX_HYBRID_ELITE_CERTIFIED_HISTORY_V1",
               "source": "CERTIFIED_SETTLED_PHYSICAL_LEDGER",
               "synthetic": False, "real_money": "BLOCKED", "rows": []}
    for i in range(n):
        at = START - timedelta(days=100-i)
        history["rows"].append({
            "lane": lane, "group": "same-surface-or-league",
            "physical_event_id": f"synthetic_prior_{i}",
            "independent_identity_certified": True,
            "independent_outcome_certified": True,
            "pre_event_features_certified": True,
            "source_timestamp_immutable": True,
            "outcome": i % 2,
            "event_start_at_utc": at.isoformat(),
            "independently_certified_final_at_utc": (at + timedelta(hours=2)).isoformat(),
        })
    request = {"schema": "MATRIX_HYBRID_ELITE_BAYESIAN_RESEARCH_REQUEST_V1",
               "real_money": "BLOCKED", "automatic_wagering": False,
               "synthetic": False, "targets": [{
                   "lane": lane, "group": "same-surface-or-league",
                   "physical_event_id": "synthetic_future",
                   "prematch_or_live_identity_certified": True,
                   "target_features_pit_certified": True,
                   "prediction_frozen_at_utc": (START - timedelta(hours=1)).isoformat(),
                   "event_start_at_utc": START.isoformat(),
               }]}
    return history, request


def test_pre_cut_bayesian_estimate_is_isolated():
    history, request = docs()
    r = build(history, request)
    row = r["targets"][0]
    assert row["certified_histories_available_before_freeze"] == 35
    assert row["status"] == "RESEARCH_ONLY_PROSPECTIVE_BAYESIAN_PROBABILITY"
    assert 0 < row["p_bayesian_research_only"] < 1
    assert row["governed_p_matrix_authorized"] is False
    assert r["original_matrix_parameters_modified"] is False
    assert r["automatic_wagering"] is False
    assert r["real_money"] == "BLOCKED"


def test_not_enough_history_returns_null_probability():
    history, request = docs(6)
    r = build(history, request)["targets"][0]
    assert r["status"] == "RESEARCH_ONLY_INSUFFICIENT_CERTIFIED_HISTORY"
    assert r["p_bayesian_research_only"] is None


def test_history_settled_after_forecast_cannot_enter_model():
    history, request = docs(35)
    for i in range(10):
        history["rows"][i]["independently_certified_final_at_utc"] = (
            START + timedelta(hours=i+1)).isoformat()
    r = build(history, request)["targets"][0]
    assert r["certified_histories_available_before_freeze"] == 25
    assert r["p_bayesian_research_only"] is None


def test_duplicate_historical_event_fails_closed():
    history, request = docs()
    history["rows"].append(deepcopy(history["rows"][0]))
    with pytest.raises(ValueError, match="BAYESIAN_DUPLICATE_HISTORY_ID"):
        build(history, request)


def test_uncertified_result_rejected():
    history, request = docs()
    history["rows"][0]["independent_outcome_certified"] = False
    with pytest.raises(ValueError, match="BAYESIAN_UNCERTIFIED_HISTORY_ROW"):
        build(history, request)


def test_prematch_forecast_after_start_rejected():
    history, request = docs()
    request["targets"][0]["prediction_frozen_at_utc"] = (
        START + timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError, match="BAYESIAN_PREMATCH_PIT_LEAKAGE"):
        build(history, request)


def test_live_requires_inplay_and_before_real_event_end():
    history, request = docs(35, lane="TENNIS_LIVE")
    item = request["targets"][0]
    item["prediction_frozen_at_utc"] = (START + timedelta(minutes=25)).isoformat()
    item["independently_certified_end_at_utc"] = (
        START + timedelta(hours=2)).isoformat()
    assert build(history, request)["targets"][0]["p_bayesian_research_only"] is not None
    item["independently_certified_end_at_utc"] = (
        START + timedelta(minutes=20)).isoformat()
    with pytest.raises(ValueError, match="BAYESIAN_LIVE_PIT_LEAKAGE"):
        build(history, request)


def test_a_future_outcome_is_not_a_training_label():
    history, request = docs(35)
    request["targets"][0]["physical_event_id"] = history["rows"][0]["physical_event_id"]
    with pytest.raises(ValueError, match="BAYESIAN_DUPLICATE_OR_SETTLED_TARGET_ID"):
        build(history, request)


def test_synthetic_flag_on_real_input_rejected():
    history, request = docs()
    history["synthetic"] = True
    with pytest.raises(ValueError, match="BAYESIAN_UNTRUSTED_SOURCE"):
        build(history, request)


def test_wrong_history_time_order_fails_closed():
    history, request = docs()
    history["rows"][0]["independently_certified_final_at_utc"] = (
        history["rows"][0]["event_start_at_utc"])
    with pytest.raises(ValueError, match="BAYESIAN_HISTORICAL_FINAL_ORDER"):
        build(history, request)


import hashlib
import json
from tools.matrix_hybrid_elite_bayesian_shadow import verify_physical_receipts


def physical_source_docs(tmp_path):
    history, request = docs(1)
    for kind, items in (("HISTORY", history["rows"]), ("REQUEST", request["targets"])):
        for index, item in enumerate(items):
            receipt = dict(item, schema="MATRIX_HYBRID_ELITE_BAYESIAN_"
                           + kind + "_RECEIPT_V1", real_money="BLOCKED")
            original = tmp_path / f"{kind.lower()}_{index}.json"
            original.write_text(json.dumps(receipt, sort_keys=True))
            item["original_receipt_path"] = original.name
            item["original_receipt_sha256"] = hashlib.sha256(
                original.read_bytes()).hexdigest()
    return history, request


def test_bayesian_source_receipts_prove_actual_bytes(tmp_path):
    history, request = physical_source_docs(tmp_path)
    report = verify_physical_receipts(
        history, request, history_root=tmp_path, request_root=tmp_path)
    assert report["physical_sha_bound_receipts_verified"] == 2
    assert report["automatic_model_promotion"] is False
    assert build(history, request)["targets"][0]["p_bayesian_research_only"] is None


def test_bayesian_history_tampering_is_detected(tmp_path):
    history, request = physical_source_docs(tmp_path)
    original = tmp_path / history["rows"][0]["original_receipt_path"]
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(ValueError, match="BAYESIAN_ORIGINAL_RECEIPT_HASH_CONFLICT"):
        verify_physical_receipts(history, request, history_root=tmp_path,
                                 request_root=tmp_path)


def test_bayesian_forged_history_outcome_even_with_rehashed_receipt_is_blocked(tmp_path):
    history, request = physical_source_docs(tmp_path)
    path = tmp_path / history["rows"][0]["original_receipt_path"]
    receipt = json.loads(path.read_text())
    receipt["outcome"] = 1 - receipt["outcome"]
    path.write_text(json.dumps(receipt, sort_keys=True))
    history["rows"][0]["original_receipt_sha256"] = hashlib.sha256(
        path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="BAYESIAN_ORIGINAL_HISTORY_VALUE_CONFLICT"):
        verify_physical_receipts(history, request, history_root=tmp_path,
                                 request_root=tmp_path)


def test_bayesian_unbound_training_row_fails_closed(tmp_path):
    history, request = physical_source_docs(tmp_path)
    del history["rows"][0]["original_receipt_sha256"]
    with pytest.raises(ValueError, match="BAYESIAN_ORIGINAL_RECEIPT_REQUIRED"):
        verify_physical_receipts(history, request, history_root=tmp_path,
                                 request_root=tmp_path)


def test_bayesian_forged_target_freeze_fails_closed(tmp_path):
    history, request = physical_source_docs(tmp_path)
    path = tmp_path / request["targets"][0]["original_receipt_path"]
    receipt = json.loads(path.read_text())
    receipt["prediction_frozen_at_utc"] = (
        START + timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(receipt, sort_keys=True))
    request["targets"][0]["original_receipt_sha256"] = hashlib.sha256(
        path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="BAYESIAN_ORIGINAL_TARGET_VALUE_CONFLICT"):
        verify_physical_receipts(history, request, history_root=tmp_path,
                                 request_root=tmp_path)


def test_bayesian_receipt_path_traversal_rejected(tmp_path):
    history, request = physical_source_docs(tmp_path)
    request["targets"][0]["original_receipt_path"] = "../outside.json"
    with pytest.raises(ValueError, match="BAYESIAN_RECEIPT_PATH_UNSAFE"):
        verify_physical_receipts(history, request, history_root=tmp_path,
                                 request_root=tmp_path)


def test_bayesian_zero_rows_does_not_claim_probabilities(tmp_path):
    history, request = docs(0)
    request["targets"] = []
    report = verify_physical_receipts(history, request,
                                     history_root=tmp_path, request_root=tmp_path)
    assert report["physical_sha_bound_receipts_verified"] == 0
    assert build(history, request)["targets"] == []
