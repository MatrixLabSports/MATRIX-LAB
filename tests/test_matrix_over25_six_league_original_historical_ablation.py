"""Tests for historical original-canonical ablation (never model promotion)."""
import json
from pathlib import Path

import pytest

import tools.matrix_over25_six_league_original_historical_ablation as m


def fake_cycle(tmp_path):
    path=tmp_path/"cycle"
    root=path/"canonical_analysis"
    root.mkdir(parents=True)
    (root/"manifest.json").write_text(json.dumps({
        "provider":"api_football", "status":"PASS",
        "real_money":"BLOCKED", "p_matrix_status":"NOT_GENERATED",
        "model_probability_generated":False,
        "analysis_as_of_utc":"2026-10-24T09:40:17+00:00"
    }))
    for league in m.SIX:
        group=path/"history"/"raw"/f"league_{league}_season_2026.bin"
        group.parent.mkdir(parents=True,exist_ok=True)
        group.write_bytes(b'{"response":[]}')
    return path


def sample(league,changed=1):
    return {
        "canonical_targets":2,
        "paired_targets":2,
        "probability_changed_targets":changed,
        "probability_identical_targets":2-changed,
        "blocked_targets":0,
        "maximum_probability_difference":0.03 if changed else 0.0,
        "reference_canonical_bundle_sha256":"a"*64,
        "rows":[
            {"fixture_id":f"{league}:1",
             "reference_status":"PAIRED_ARCHIVED_REPLAY_ONLY",
             "same_probability_with_group_only":False,
             "absolute_probability_delta":0.03,
             "enriched_history_source":{"home":"CANONICAL_ENRICHED_PIT"}}
        ] if changed else []
    }


def test_historical_original_ablation_never_authorizes_production(tmp_path,monkeypatch):
    cycle=fake_cycle(tmp_path)
    monkeypatch.setattr(m,"compare_cycle",lambda p,league:sample(league))
    out=m.evaluate(cycle)
    assert len(out["six_original_leagues"])==6
    assert out["historical_paired_rows"]==12
    assert out["historical_probability_changed_rows"]==6
    assert out["historical_substitution_equivalent_for_all_replayed"] is False
    assert out["no_cross_provider_fixture_parity_certified"] is True
    assert out["historical_reconstruction_is_not_prospective_freeze"] is True
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False
    assert out["real_money"]=="BLOCKED"


def test_missing_raw_group_is_blocked_not_replaced_by_zero(tmp_path,monkeypatch):
    cycle=fake_cycle(tmp_path)
    (cycle/"history"/"raw"/"league_39_season_2026.bin").unlink()
    monkeypatch.setattr(m,"compare_cycle",lambda p,league:sample(league,0))
    out=m.evaluate(cycle)
    assert out["source_group_missing_league_ids"]==["39"]
    assert out["six_original_leagues"][0]["probability_changed_targets"] is None
    assert out["historical_substitution_equivalent_for_all_replayed"] is False


def test_unsafe_manifest_is_rejected_before_any_comparison(tmp_path,monkeypatch):
    cycle=fake_cycle(tmp_path)
    manifest=cycle/"canonical_analysis"/"manifest.json"
    value=json.loads(manifest.read_text())
    value["model_probability_generated"]=True
    manifest.write_text(json.dumps(value))
    monkeypatch.setattr(m,"compare_cycle",lambda p,league:pytest.fail("must not replay"))
    with pytest.raises(ValueError,match="ORIGINAL_ARCHIVE_NOT_SAFE_RESEARCH_INPUT"):
        m.evaluate(cycle)


def test_inconsistent_replay_counts_block_report(tmp_path,monkeypatch):
    cycle=fake_cycle(tmp_path)
    def bad(p,league):
        item=sample(league)
        item["probability_changed_targets"]=3
        return item
    monkeypatch.setattr(m,"compare_cycle",bad)
    with pytest.raises(ValueError,match="HISTORICAL_ABLATION_COUNT_INCONSISTENT"):
        m.evaluate(cycle)
