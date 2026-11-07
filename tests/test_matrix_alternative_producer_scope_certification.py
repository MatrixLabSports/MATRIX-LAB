"""Evidence-based scoped certification; never promotes research into production."""
import copy
import json
from pathlib import Path

import pytest

from tools.matrix_alternative_producer_scope_certification import certify, digest, read_object

ROOT = Path("evidence/football_world_inventory/2026-11-04")
HIST = ROOT / "MATRIX_INDEPENDENT_OVER25_HISTORICAL_PARITY.json"
PROSP = ROOT / "MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_41735756927.json"


def test_real_historical_replay_certifies_only_raw_group_scope():
    hist,prosp=read_object(HIST),read_object(PROSP)
    result=certify(hist,prosp,digest(HIST),digest(PROSP))
    assert result["status"]=="PASS_SCOPED_HISTORICAL_RAW_GROUP_ONLY_PRODUCTION_BLOCKED"
    assert result["historical_scope"]["matched_results"]==75
    assert result["historical_scope"]["scoreable_raw_group_pairs"]==30
    assert result["historical_scope"]["identical_raw_group_pairs"]==30
    assert result["historical_scope"]["certified"] is True
    assert result["prospective_scope"]["fixtures"]==3
    assert result["full_alternative_producer_certified"] is False
    assert result["production_p_matrix_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["original_calibration_untouched"] is True
    assert result["real_money"]=="BLOCKED"


def test_changing_one_historical_probability_difference_revokes_partial_pass():
    hist=copy.deepcopy(read_object(HIST))
    hist["raw_group_feature_parity"]["different_raw_group_feature_or_probability_count"]=1
    result=certify(hist,read_object(PROSP),digest(HIST),digest(PROSP))
    assert result["historical_scope"]["certified"] is False
    assert result["full_alternative_producer_certified"] is False


def test_original_model_parity_false_cannot_be_faked():
    hist=copy.deepcopy(read_object(HIST))
    hist["calibrated_model_feature_equivalence_verified"]=True
    result=certify(hist,read_object(PROSP),digest(HIST),digest(PROSP))
    assert result["historical_scope"]["certified"] is False
    assert result["production_p_matrix_authorized"] is False


def test_any_prospective_probability_promotion_rejected():
    prosp=copy.deepcopy(read_object(PROSP))
    prosp["rows"][0]["governed_probability_authorized"]=True
    with pytest.raises(ValueError,match="UNAUTHORIZED_PROSPECTIVE"):
        certify(read_object(HIST),prosp,digest(HIST),digest(PROSP))


def test_invalid_evidence_or_governance_rejected():
    hist=copy.deepcopy(read_object(HIST));hist["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="GOVERNANCE"):
        certify(hist,read_object(PROSP),digest(HIST),digest(PROSP))
    with pytest.raises(ValueError,match="SHA256"):
        certify(read_object(HIST),read_object(PROSP),"BAD",digest(PROSP))
