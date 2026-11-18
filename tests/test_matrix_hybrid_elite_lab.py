"""Synthetic-only strict validation of isolated MATRIX Hybrid Elite laboratory."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from tools.matrix_hybrid_elite_lab import evaluate, validate, metrics

UTC = timezone.utc


def example(n=2, lane="FOOTBALL_OVER25"):
    start = datetime(2026, 9, 1, 18, tzinfo=UTC)
    rows = []
    for i in range(n):
        kickoff = start + timedelta(days=i)
        frozen = kickoff - timedelta(hours=2)
        settled = kickoff + timedelta(hours=3)
        y = i % 2
        rows.append({
            "lane": lane, "physical_event_id": f"synthetic_{i}",
            "prospective_identity_certified": True,
            "original_feature_pit_certified": True,
            "independent_outcome_certified": True,
            "source_timestamp_immutable": True,
            "prediction_frozen_at_utc": frozen.isoformat(),
            "event_start_at_utc": kickoff.isoformat(),
            "outcome_certified_at_utc": settled.isoformat(),
            "outcome": y,
            "p_matrix_frozen": 0.6 if y else 0.4,
            "contenders": {
                "bayesian_shadow": {
                    "p_frozen": 0.8 if y else 0.2,
                    "training_closed_at_utc": (frozen - timedelta(days=1)).isoformat(),
                }
            },
        })
    return {
        "schema": "MATRIX_HYBRID_ELITE_PROSPECTIVE_INPUT_V1",
        "source": "CERTIFIED_PROSPECTIVE_LEDGER",
        "synthetic": False, "real_money": "BLOCKED",
        "automatic_wagering": False,
        "original_model_parameters_modified": False,
        "rows": rows,
    }


def test_small_sample_never_claims_screen_winner():
    result = evaluate(example(4))
    lane = next(x for x in result["lanes"] if x["lane"] == "FOOTBALL_OVER25")
    contender = lane["challengers"][0]
    assert contender["delta_brier_matrix_minus_challenger"] > 0
    assert contender["sufficient_historical_holdout_to_consider"] is False
    assert contender["metrics_pass_screen_not_authorization"] is False
    assert result["any_model_promoted"] is False
    assert result["telegram_signal_authorized"] is False


def test_large_synthetic_only_exercises_metrics_and_never_promotes():
    result = evaluate(example(200))
    contender = next(x for x in result["lanes"] if x["lane"] == "FOOTBALL_OVER25")["challengers"][0]
    assert contender["sufficient_historical_holdout_to_consider"] is True
    assert contender["metrics_pass_screen_not_authorization"] is True
    assert contender["independent_reproducible_prospective_replication_verified"] is False
    assert contender["automatically_promoted"] is False
    assert result["any_model_promoted"] is False


def test_empty_certified_cohort_has_no_winner():
    d = example(0)
    result = evaluate(d)
    assert result["certified_total_events"] == 0
    assert all(x["matrix_original"] is None for x in result["lanes"])
    assert all(not x["challengers"] for x in result["lanes"])


def test_duplicate_physical_match_rejected_in_same_lane():
    d = example()
    d["rows"].append(deepcopy(d["rows"][0]))
    with pytest.raises(ValueError, match="LAB_DUPLICATE_PHYSICAL_EVENT"):
        validate(d)


@pytest.mark.parametrize("key", [
    "prospective_identity_certified",
    "original_feature_pit_certified",
    "independent_outcome_certified",
    "source_timestamp_immutable",
])
def test_missing_source_certification_fails_closed(key):
    d = example()
    d["rows"][0][key] = False
    with pytest.raises(ValueError, match="LAB_UNCERTIFIED_PROSPECTIVE_ROW"):
        validate(d)


def test_post_match_prediction_rejected():
    d = example()
    d["rows"][0]["prediction_frozen_at_utc"] = d["rows"][0]["outcome_certified_at_utc"]
    with pytest.raises(ValueError, match="LAB_PIT_OR_OUTCOME_TIME_LEAKAGE"):
        validate(d)


def test_training_after_forecast_rejected():
    d = example()
    d["rows"][0]["contenders"]["bayesian_shadow"]["training_closed_at_utc"] = (
        d["rows"][0]["event_start_at_utc"])
    with pytest.raises(ValueError, match="LAB_CHALLENGER_TRAINED_AFTER_FORECAST"):
        validate(d)


def test_live_requires_independently_attested_inplay_and_real_end():
    d = example(1, lane="TENNIS_LIVE")
    with pytest.raises(KeyError):
        validate(d)
    row = d["rows"][0]
    kickoff = datetime.fromisoformat(row["event_start_at_utc"])
    row["prediction_frozen_at_utc"] = (kickoff + timedelta(minutes=15)).isoformat()
    row["contenders"]["bayesian_shadow"]["training_closed_at_utc"] = (
        kickoff - timedelta(days=1)).isoformat()
    row["independently_certified_event_end_at_utc"] = (
        kickoff + timedelta(hours=2)).isoformat()
    assert len(validate(d)) == 1
    row["independently_certified_event_end_at_utc"] = row["prediction_frozen_at_utc"]
    with pytest.raises(ValueError, match="LAB_LIVE_END_CHRONOLOGY_NOT_CERTIFIED"):
        validate(d)
    row["prediction_frozen_at_utc"] = (kickoff - timedelta(minutes=5)).isoformat()
    row["independently_certified_event_end_at_utc"] = (
        kickoff + timedelta(hours=2)).isoformat()
    with pytest.raises(ValueError, match="LAB_LIVE_END_CHRONOLOGY_NOT_CERTIFIED"):
        validate(d)


def test_no_synthetic_dataset_authorized_as_real_input():
    d = example(1)
    d["synthetic"] = True
    with pytest.raises(ValueError, match="LAB_UNTRUSTED_PROSPECTIVE_INPUT"):
        validate(d)


def test_market_probability_labels_must_be_finite():
    d = example(1)
    d["rows"][0]["p_matrix_frozen"] = float("nan")
    with pytest.raises(ValueError, match="LAB_PROBABILITY_OUT_OF_RANGE"):
        validate(d)


def test_brier_and_logloss_are_proper_scoring_rules():
    good = metrics([(0.8, 1), (0.2, 0)])
    bad = metrics([(0.2, 1), (0.8, 0)])
    assert good["brier"] < bad["brier"]
    assert good["logloss"] < bad["logloss"]

import hashlib
import json
from tools.matrix_hybrid_elite_lab import verify_original_receipts

def with_sha_receipts(tmp_path):
    d = example(1)
    row = d["rows"][0]
    pred = {
        "schema": "MATRIX_HYBRID_ELITE_PREDICTION_RECEIPT_V1",
        "lane": row["lane"],
        "physical_event_id": row["physical_event_id"],
        "real_money": "BLOCKED",
        "frozen_at_utc": row["prediction_frozen_at_utc"],
        "p_matrix_frozen": row["p_matrix_frozen"],
        "contenders": {k:v["p_frozen"] for k,v in row["contenders"].items()},
        "original_feature_pit_certified": True,
        "prospective_identity_certified": True,
    }
    final = {
        "schema": "MATRIX_HYBRID_ELITE_OUTCOME_RECEIPT_V1",
        "lane": row["lane"], "physical_event_id": row["physical_event_id"],
        "real_money": "BLOCKED",
        "certified_at_utc": row["outcome_certified_at_utc"],
        "outcome": row["outcome"],
        "independent_outcome_certified": True,
    }
    paths = []
    for typ, body in (("prediction",pred),("outcome",final)):
        path=tmp_path/(typ+".json")
        path.write_text(json.dumps(body))
        row[typ+"_receipt_path"]=path.name
        row[typ+"_receipt_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
        paths.append(path)
    return d, paths


def test_real_cli_receipt_gate_rejects_missing_originals(tmp_path):
    d=example(1)
    with pytest.raises(ValueError,match="LAB_ORIGINAL_SOURCE_RECEIPT_REQUIRED"):
        verify_original_receipts(d,tmp_path)


def test_hash_bound_prediction_and_outcome_rows_pass_only_source_gate(tmp_path):
    d,paths=with_sha_receipts(tmp_path)
    result=verify_original_receipts(d,tmp_path)
    assert result["verified_receipt_files"]==2
    assert result["paired_certified_source_rows"]==1
    assert result["model_promotion_authorized"] is False


def test_tampered_prediction_receipt_fails_closed(tmp_path):
    d,paths=with_sha_receipts(tmp_path)
    paths[0].write_bytes(paths[0].read_bytes()+b" ")
    with pytest.raises(ValueError,match="LAB_ORIGINAL_SOURCE_RECEIPT_TAMPERED"):
        verify_original_receipts(d,tmp_path)


def test_forged_prediction_value_under_matching_hash_is_rejected(tmp_path):
    d,paths=with_sha_receipts(tmp_path)
    p=json.loads(paths[0].read_text())
    p["p_matrix_frozen"]=0.01
    paths[0].write_text(json.dumps(p))
    d["rows"][0]["prediction_receipt_sha256"]=hashlib.sha256(paths[0].read_bytes()).hexdigest()
    with pytest.raises(ValueError,match="LAB_PREDICTION_RECEIPT_VALUE_MISMATCH"):
        verify_original_receipts(d,tmp_path)


def test_outcome_from_other_physical_event_rejected(tmp_path):
    d,paths=with_sha_receipts(tmp_path)
    p=json.loads(paths[1].read_text())
    p["physical_event_id"]="different_fixture"
    paths[1].write_text(json.dumps(p))
    d["rows"][0]["outcome_receipt_sha256"]=hashlib.sha256(paths[1].read_bytes()).hexdigest()
    with pytest.raises(ValueError,match="LAB_ORIGINAL_SOURCE_RECEIPT_IDENTITY_MISMATCH"):
        verify_original_receipts(d,tmp_path)


def test_source_path_escape_is_rejected(tmp_path):
    d,paths=with_sha_receipts(tmp_path)
    d["rows"][0]["prediction_receipt_path"]="../outside.json"
    with pytest.raises(ValueError,match="LAB_ORIGINAL_SOURCE_PATH_UNSAFE"):
        verify_original_receipts(d,tmp_path)


def test_receipt_gate_accepts_empty_cohort_without_fabricating_metrics(tmp_path):
    d=example(0)
    assert verify_original_receipts(d,tmp_path)["verified_receipt_files"]==0
    assert evaluate(d)["certified_total_events"]==0



def test_paired_bootstrap_is_reproducible_and_not_a_promotion():
    d = example(200)
    first = evaluate(d)
    second = evaluate(d)
    a = next(x for x in first["lanes"] if x["lane"] == "FOOTBALL_OVER25")["challengers"][0]
    b = next(x for x in second["lanes"] if x["lane"] == "FOOTBALL_OVER25")["challengers"][0]
    assert a["paired_uncertainty_screen"] == b["paired_uncertainty_screen"]
    assert a["paired_uncertainty_screen"]["brier_delta_lower"] > 0
    assert a["paired_uncertainty_screen"]["logloss_delta_lower"] > 0
    assert a["automatically_promoted"] is False
    assert first["any_model_promoted"] is False


def test_same_predictions_cannot_pass_statistical_screen():
    d = example(200)
    for row in d["rows"]:
        row["contenders"]["bayesian_shadow"]["p_frozen"] = row["p_matrix_frozen"]
    report = evaluate(d)
    contender = next(x for x in report["lanes"] if x["lane"] == "FOOTBALL_OVER25")["challengers"][0]
    assert contender["paired_uncertainty_screen"]["brier_delta_lower"] == 0
    assert contender["paired_uncertainty_screen"]["logloss_delta_lower"] == 0
    assert contender["metrics_pass_screen_not_authorization"] is False


def test_insufficient_samples_have_no_confidence_claim():
    report = evaluate(example(40))
    contender = next(x for x in report["lanes"] if x["lane"] == "FOOTBALL_OVER25")["challengers"][0]
    assert contender["paired_uncertainty_screen"] is None
    assert contender["metrics_pass_screen_not_authorization"] is False
