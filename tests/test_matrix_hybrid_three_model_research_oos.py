"""Research-only three-model evaluation tests. Synthetic labels are tests, never bets."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import matrix_hybrid_three_model_research_oos as m

ROOT = Path(__file__).resolve().parents[1]
FUTURE = datetime(2026, 11, 20, 6, tzinfo=timezone.utc)


def sample():
    pair = {
        "physical_event_id": "560643",
        "competition_id": "2021",
        "event_start_at_utc": "2026-11-21T12:30:00+00:00",
        "original_formula_research_p": 0.5063354725,
        "independent_free_poisson_p": 0.485329542936,
        "original_freeze_sha256": "a"*64,
        "poisson_freeze_sha256": "b"*64,
        "common_history_raw_sha256": "c"*64,
        "original_formula_research_frozen_at_utc": "2026-11-19T09:05:56+00:00",
        "independent_poisson_frozen_at_utc": "2026-11-19T09:05:57+00:00",
    }
    b = {
        "schema": "MATRIX_HYBRID_FREE_BAYESIAN_OVER25_RESEARCH_V1",
        "model_id": "MATRIX_HYBRID_FREE_BAYESIAN_OVER25_V1",
        "physical_event_id": pair["physical_event_id"],
        "provider_competition_id": pair["competition_id"],
        "provider": "FOOTBALL_DATA_ORG",
        "source_original_research_freeze_sha256": pair["original_freeze_sha256"],
        "source_independent_poisson_freeze_sha256": pair["poisson_freeze_sha256"],
        "same_authenticated_target_history_sha256": pair["common_history_raw_sha256"],
        "source_history_response_sha256_by_competition": {
            pair["competition_id"]: pair["common_history_raw_sha256"],
        },
        "event_start_at_utc": pair["event_start_at_utc"],
        "forecast_frozen_at_utc": "2026-11-19T09:50:00+00:00",
        "target_outcome_not_used": True,
        "model_promotion_authorized": False,
        "independent_hybrid_future_oos_certified": False,
        "p_bayesian_research_over25": 0.55,
        "certified_before_prediction_league_count": 100,
        "certified_before_prediction_historical_pool_count": 450,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    y = {
        "fixture_id": pair["physical_event_id"],
        "provider_competition_id": pair["competition_id"],
        "original_frozen_forecast_sha256": pair["original_freeze_sha256"],
        "poisson_forecast_sha256": pair["poisson_freeze_sha256"],
        "poisson_source_history_sha256": pair["common_history_raw_sha256"],
        "original_source_history_sha256": pair["common_history_raw_sha256"],
        "identical_authenticated_history_capture": True,
        "settlement_sha256": "d"*64,
        "provider_result_sha256": "e"*64,
        "outcome": 1,
        "original_research_p": pair["original_formula_research_p"],
        "poisson_p": pair["independent_free_poisson_p"],
    }
    return pair, b, y


def put(root, pair, bayesian):
    file = m.bayesian_file(root, pair)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(bayesian, sort_keys=True)+"\n", encoding="utf-8")
    return file


def test_three_model_predictions_share_event_without_winner_promotion(tmp_path):
    pair, bayes, actual = sample()
    put(tmp_path, pair, bayes)
    bound = m.verify_bayesian(tmp_path, pair, FUTURE)
    scored = m.compare_one(pair, actual, bound)
    assert scored["fixture_id"] == pair["physical_event_id"]
    assert set(scored["predictors"]) == set(m.PREDICTORS)
    assert scored["same_authenticated_input"] is True
    assert scored["outcome_over25"] == 1
    assert abs(scored["predictors"]["hybrid_free_bayesian"]["brier"]-0.45**2)<1e-12
    assert m.aggregate([scored])["independent_free_poisson"]["mean_brier"] > 0
    assert scored["source_bayesian_forecast_sha256"] == m.digest(
        m.bayesian_file(tmp_path, pair))


def test_altered_bayesian_source_sha_is_rejected(tmp_path):
    pair, bayes, _ = sample()
    bayes["same_authenticated_target_history_sha256"] = "z"*64
    put(tmp_path, pair, bayes)
    with pytest.raises(ValueError, match="BAYESIAN_SOURCE_PROVENANCE_MISMATCH"):
        m.verify_bayesian(tmp_path, pair, FUTURE)


def test_post_kickoff_bayesian_forecast_is_rejected(tmp_path):
    pair, bayes, _ = sample()
    bayes["forecast_frozen_at_utc"] = "2026-11-21T14:00:00+00:00"
    put(tmp_path, pair, bayes)
    with pytest.raises(ValueError, match="BAYESIAN_NOT_AUTHENTIC_PREMATCH_FREEZE"):
        m.verify_bayesian(tmp_path, pair, datetime(2026, 11, 22, tzinfo=timezone.utc))


def test_tampered_original_p_matrix_sha_is_rejected(tmp_path):
    pair, bayes, row = sample()
    put(tmp_path, pair, bayes)
    bound = m.verify_bayesian(tmp_path, pair, FUTURE)
    row["original_frozen_forecast_sha256"] = "0"*64
    with pytest.raises(ValueError, match="VERIFIED_OUTCOME_RESEARCH_SOURCE_NOT_IDENTICAL"):
        m.compare_one(pair, row, bound)


def test_unverified_result_not_accepted_without_source_hashes(tmp_path):
    pair, bayes, row = sample()
    put(tmp_path, pair, bayes)
    bound = m.verify_bayesian(tmp_path, pair, FUTURE)
    row["provider_result_sha256"] = ""
    with pytest.raises(ValueError, match="VERIFIED_OUTCOME_UNBOUND_RESULT_SHA"):
        m.compare_one(pair, row, bound)


def test_model_admission_cannot_be_flagged_by_caller(tmp_path):
    pair, bayes, _ = sample()
    bayes["telegram_signal_authorized"] = True
    put(tmp_path, pair, bayes)
    with pytest.raises(ValueError, match="FORECAST_ILLEGAL_PROMOTION"):
        m.verify_bayesian(tmp_path, pair, FUTURE)


def test_real_2026_11_21_cannot_have_any_settled_results_before_kickoff():
    result = m.evaluate(ROOT, FUTURE)
    assert result["prospective_paired_research_fixture_count"] == 37
    assert result["three_model_authenticated_settled_count"] == 0
    assert result["three_model_rejected"] == []
    assert (result["three_model_pending_fixture_count"] +
            len(result["three_model_missing_bayesian_forecasts"]) == 37)
    assert result["pooled_results"] is None
    assert result["model_winner_authorized"] is False
    assert result["original_official_p_matrix_present"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"] == "BLOCKED"
