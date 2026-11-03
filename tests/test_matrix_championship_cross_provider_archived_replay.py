"""Physical archived-source parity, strictly historical and never production."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from tools.matrix_championship_cross_provider_archived_replay import audit

ROOT=Path(__file__).resolve().parents[1]
SHADOW=ROOT/"evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"

def load():
    return json.loads(SHADOW.read_text(encoding="utf-8"))

def test_real_authentic_independent_http_vs_original_frozen_archive():
    d=audit(load())
    assert d["network_calls"]==0
    assert d["reference_fixture_count"]>=20
    assert d["matched_historical_result_count"]>=20
    assert d["historical_result_disagreements"]==0
    assert d["current_fixture_crosswalk_verified"] is False
    assert d["canonical_enriched_pit_equivalence_verified"] is False
    assert d["full_original_calibrated_model_equivalence_verified"] is False
    assert d["new_production_p_matrix_authorized"] is False
    assert d["telegram_signal_authorized"] is False
    assert d["real_money"]=="BLOCKED"

def test_rejects_tampered_bytes_while_keep_original_hash():
    shadow=load()
    evidence=shadow["authenticated_raw_group_replay_evidence"]["2016"]
    evidence["response_base64"]=evidence["response_base64"][:-8]+"AAAAAAAA"
    with pytest.raises(ValueError,match="HTTP_PROVENANCE"):
        audit(shadow)

def test_rejects_unverified_provider_scope_without_reading_archive():
    shadow=load()
    shadow["source"]="API_FOOTBALL"
    with pytest.raises(ValueError,match="GOVERNANCE"):
        audit(shadow)

def test_missing_original_authenticated_group_is_never_equivalent():
    shadow=load()
    shadow["authenticated_raw_group_replay_evidence"].pop("2016")
    with pytest.raises(ValueError,match="MISSING_AUTHENTIC_HTTP"):
        audit(shadow)
