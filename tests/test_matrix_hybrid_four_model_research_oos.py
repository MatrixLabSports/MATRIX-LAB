"""Prospective four-way research evaluator tests; invented labels stay in tests."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from tools import matrix_hybrid_four_model_research_oos as four
from tools import matrix_hybrid_three_model_research_oos as three
from tools import matrix_hybrid_original_dual_freeze_lineage as lineage

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/"evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json"
NOW = datetime(2026,11,20,6,tzinfo=timezone.utc)


def pair():
    return json.loads(MANIFEST.read_bytes())["prelabel_research_pairs"][0]


def test_real_37_frozen_four_model_research_cohort_no_future_outcomes():
    r=four.evaluate(ROOT,NOW)
    assert r["physical_prelabeled_fixture_count"] == 37
    assert r["verified_original_dual_freeze_lineages"] == 37
    assert r["four_model_frozen_future_count"] == 37
    assert r["four_model_verified_settled_count"] == 0
    assert len(r["four_model_missing_v2_forecasts"]) == 0
    assert len(r["four_model_rejected"]) == 0
    assert r["global_metrics"] is None
    assert r["model_superiority_claim_authorized"] is False
    assert r["automatic_model_promotion"] is False
    assert r["telegram_signal_authorized"] is False
    assert r["real_money"] == "BLOCKED"


def test_actual_v2_sha_bound_and_before_kickoff():
    p=pair()
    item=four.v2_forecast(ROOT,p,NOW)
    assert item is not None
    assert item["p"]>0 and item["p"]<1
    assert len(item["file_sha256"])==64


def test_wrong_source_history_blocks_v2_prospective_admission():
    p=pair()
    p["common_history_raw_sha256"]="0"*64
    with pytest.raises(ValueError,match="TEAM_V2_SHA_SOURCE_LINEAGE_MISMATCH"):
        four.v2_forecast(ROOT,p,NOW)


def test_post_kickoff_modified_clock_would_block_real_v2(tmp_path):
    p=pair()
    src=four.v2_path(ROOT,p)
    file=four.v2_path(tmp_path,p)
    file.parent.mkdir(parents=True,exist_ok=True)
    j=json.loads(src.read_bytes())
    j["forecast_frozen_at_utc"]="2026-11-21T23:00:00Z"
    file.write_text(json.dumps(j)+"\n",encoding="utf-8")
    with pytest.raises(ValueError,match="TEAM_V2_FORECAST_NOT_PROSPECTIVE"):
        four.v2_forecast(tmp_path,p,datetime(2026,11,23,tzinfo=timezone.utc))


def test_same_verified_label_four_model_scores_only_once():
    p=pair()
    v2=four.v2_forecast(ROOT,p,NOW)
    source=lineage.compare(ROOT,p)
    outcome={
        "fixture_id":str(p["physical_event_id"]),
        "competition_id":str(p["competition_id"]),
        "outcome_over25":1,
        "source_original_forecast_sha256":source[
            "selected_research_forecast_file_sha256"],
        "source_primary_settlement_original_forecast_sha256":source[
            "earliest_forecast_file_sha256"],
        "source_provider_final_sha256":"a"*64,
        "source_settlement_sha256":"b"*64,
        "source_poisson_forecast_sha256":p["poisson_freeze_sha256"],
        "source_bayesian_forecast_sha256":"c"*64,
        "predictors":{
            "original_formula_research":{"p_over25":0.5},
            "independent_free_poisson":{"p_over25":0.45},
            "hybrid_free_bayesian":{"p_over25":0.55},
        },
    }
    row=four.score_pair(outcome,v2,source)
    assert row["physical_observation_increment"]==1
    assert set(row["predictors"])==set(four.MODELS)
    assert 0<row["predictors"]["hybrid_team_venue_beta_v2"]["brier"]<1
    assert four.stats([row])["original_formula_research"]["logloss"]>0


def test_unmatched_primary_forecast_not_equated_to_research_pair():
    p=pair()
    v2=four.v2_forecast(ROOT,p,NOW)
    source=lineage.compare(ROOT,p)
    outcome={
        "fixture_id":str(p["physical_event_id"]),
        "outcome_over25":1,
        "source_original_forecast_sha256":"0"*64,
    }
    with pytest.raises(ValueError,match="FOUR_MODEL_EARLIEST_FREEZE_LINEAGE_NOT_VERIFIED"):
        four.score_pair(outcome,v2,source)
