from datetime import datetime, timezone
from pathlib import Path

import pytest
import tools.matrix_over25_enriched_vs_group_parity as m


def test_parity_replay_exposes_unequal_enriched_history_without_promoting(monkeypatch,tmp_path):
    fixture={"fixture_id":"123","kickoff_utc":"2026-10-25T12:00:00+00:00",
             "competition_id":"40","season":2026,"canonical_sha256":"a"*64,
             "home_history":[{"goals_for":3}],"away_history":[{"goals_for":2}]}
    manifest={"provider":"api_football","status":"PASS","real_money":"BLOCKED",
              "p_matrix_status":"NOT_GENERATED",
              "analysis_as_of_utc":"2026-10-24T09:40:17+00:00",
              "bundle_sha256":"abc"}
    monkeypatch.setattr(m,"load_chunked_canonical_bundle",lambda root:({"inputs":[fixture]},manifest))
    group=[{"kickoff_utc":datetime(2026,10,23,tzinfo=timezone.utc)}]
    monkeypatch.setattr(m,"_load_group",lambda path:(group,"hash-of-original"))
    monkeypatch.setattr(Path,"is_file",lambda path:True)
    def features(raw_group,target):
        if target["home_history"]:
            return {"home_history_source":"CANONICAL_ENRICHED_PIT",
              "away_history_source":"CANONICAL_ENRICHED_PIT",
              "home_history_count":5,"away_history_count":5,
              "poisson":{"over_2_5":0.8},"baseline":{"over_2_5":0.55}},None
        return {"home_history_source":"RAW_GROUP_PIT",
              "away_history_source":"RAW_GROUP_PIT",
              "home_history_count":5,"away_history_count":5,
              "poisson":{"over_2_5":0.5},"baseline":{"over_2_5":0.55}},None
    monkeypatch.setattr(m,"_inputs_for_target",features)
    result=m.compare_cycle(tmp_path,"40")
    assert result["paired_targets"]==1
    assert result["probability_changed_targets"]==1
    assert result["maximum_probability_difference"]>0
    assert result["raw_group_replacement_equivalence_certified"] is False
    assert result["future_model_probability_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"]=="BLOCKED"


def test_replay_rejects_archive_after_kickoff(monkeypatch,tmp_path):
    fixture={"fixture_id":"123","kickoff_utc":"2026-10-24T08:00:00+00:00",
             "competition_id":"40","season":2026,"canonical_sha256":"a"*64}
    manifest={"provider":"api_football","status":"PASS","real_money":"BLOCKED",
              "p_matrix_status":"NOT_GENERATED",
              "analysis_as_of_utc":"2026-10-24T09:40:17+00:00","bundle_sha256":"abc"}
    monkeypatch.setattr(m,"load_chunked_canonical_bundle",lambda root:({"inputs":[fixture]},manifest))
    with pytest.raises(ValueError,match="PIT_ARCHIVE_TARGET_AFTER_KICKOFF"):
        m.compare_cycle(tmp_path,"40")


def test_replay_rejects_unpromoted_unsafe_archive(monkeypatch,tmp_path):
    monkeypatch.setattr(m,"load_chunked_canonical_bundle",lambda root:(
        {"inputs":[]},
        {"provider":"FOOTBALL_DATA_ORG","status":"PASS","real_money":"BLOCKED",
         "p_matrix_status":"NOT_GENERATED","analysis_as_of_utc":"2026-10-24T09:40:17+00:00"}))
    with pytest.raises(ValueError,match="PIT_ARCHIVE_GOVERNANCE_INVALID"):
        m.compare_cycle(tmp_path,"40")
