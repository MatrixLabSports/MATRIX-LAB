from pathlib import Path
import json

from tools.api_football_build_challenger import build_challenger


def _source():
    return json.loads(Path("evidence/api_football/model_validation/retrospective_predictions.json").read_text(encoding="utf-8"))


def test_challenger_keeps_final_holdout_sealed_and_non_monetary():
    manifest,seal=build_challenger(_source())
    assert manifest["development_count"]>0
    assert manifest["validation_count"]>0
    assert manifest["final_holdout_count"]>0
    assert manifest["holdout_outcomes_read"] is False
    assert manifest["holdout_metrics_computed"] is False
    assert manifest["holdout_status"]=="SEALED"
    assert all("outcome" not in row for row in seal["rows"])
    assert manifest["governed_engine_promoted"] is False
    assert manifest["p_matrix_generated"] is False
    assert manifest["automatic_wagering"] is False
    assert manifest["real_money"]=="BLOCKED"


def test_validation_superiority_gate_is_explicit_for_all_three_markets():
    manifest,_=build_challenger(_source())
    assert {x["market"] for x in manifest["market_reports"]}=={"1x2","over_2_5","btts"}
    if manifest["candidate_status"]=="FROZEN_CHALLENGER_AWAITING_FINAL_HOLDOUT":
        assert manifest["all_three_markets_validation_superiority"] is True
        assert all(x["validation_superiority"] for x in manifest["market_reports"])
    else:
        assert manifest["candidate_status"]=="REJECTED_ON_VALIDATION"
        assert manifest["all_three_markets_validation_superiority"] is False
