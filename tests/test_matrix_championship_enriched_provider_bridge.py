"""Historical bridge can never authorize prospective production or Telegram."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.matrix_championship_enriched_provider_bridge import replay, unique_mapping

ROOT=Path(__file__).resolve().parents[1]
SHADOW=ROOT/"evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"

def frozen_shadow():
    return json.loads(SHADOW.read_text(encoding="utf-8"))

def test_real_original_enriched_targets_aligned_at_original_pit_cutoff():
    result=replay(frozen_shadow())
    assert result["original_canonical_targets"]==11
    assert 0<=result["historical_three_way_parity_count"]<=11
    assert result["blocked_count"]+result["historical_three_way_parity_count"]==11
    assert result["mapped_historical_team_count"]>=10
    assert all(row["new_production_probability_authorized"] is False for row in result["rows"])
    assert all(row["telegram_signal_authorized"] is False for row in result["rows"])
    assert result["prospective_enriched_provider_equivalence_verified"] is False
    assert result["future_fixture_original_provider_crosswalk_verified"] is False
    assert result["production_p_matrix_authorized"] is False
    assert result["network_calls"]==0

def test_historical_team_crosswalk_conflict_drops_mapping():
    pair=[
        {"archived_api_id":"1","free_id":"a"},
        {"archived_api_id":"2","free_id":"b"},
    ]
    archived={
        "1":{"home_team_id":"api_h","away_team_id":"api_a","home_goals":1,"away_goals":2},
        "2":{"home_team_id":"api_h","away_team_id":"api_b","home_goals":3,"away_goals":2},
    }
    independent={
        "a":{"home_team_id":"free_h","away_team_id":"free_a","home_goals":1,"away_goals":2},
        "b":{"home_team_id":"free_h_wrong","away_team_id":"free_b","home_goals":3,"away_goals":2},
    }
    mapping,conflicts=unique_mapping(pair,archived,independent)
    assert "api_h" in conflicts
    assert "api_h" not in mapping

def test_tampered_authenticated_bytes_are_rejected():
    shadow=frozen_shadow()
    shadow["authenticated_raw_group_replay_evidence"]["2016"]["response_base64"]="e30="
    with pytest.raises(ValueError,match="PROVENANCE"):
        replay(shadow)

def test_source_cannot_authorize_green_telegram():
    shadow=frozen_shadow()
    shadow["market_signal_authorized"]=True
    with pytest.raises(ValueError,match="GOVERNANCE"):
        replay(shadow)
