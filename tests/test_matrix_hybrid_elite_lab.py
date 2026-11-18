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
