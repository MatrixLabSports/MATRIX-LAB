from __future__ import annotations

import json
from pathlib import Path

from tools.tennis_parallel_lane_registry import (
    initialize_lane_states,
    resolve_lane,
    validate_registry,
)


def _registry() -> dict:
    return json.loads(
        Path("config/tennis_model_lane_registry_v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_registry_has_one_protected_active_lane_and_35_parallel_lanes():
    result = validate_registry(_registry())
    assert result["status"] == "PASS"
    assert result["lane_count"] == 36
    assert result["active_governed_lane_count"] == 1
    assert result["parallel_lane_count"] == 35
    assert result["research_only_lane_count"] + result["active_prospective_lane_count"] == 35
    assert result["legacy_lane_id"] == "ATP_CHALLENGER_MEN_SINGLES_HARD"
    assert result["legacy_holdout_id"] == "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"


def test_current_cor0203_domain_routes_only_to_existing_active_lane():
    lane = resolve_lane(
        circuit="ATP_CHALLENGER",
        gender="MEN",
        event_format="SINGLES",
        surface="Hard",
        registry=_registry(),
    )
    assert lane is not None
    assert lane["lane_id"] == "ATP_CHALLENGER_MEN_SINGLES_HARD"
    assert lane["status"] == "ACTIVE_GOVERNED_COR0203"
    assert lane["feeds_cor0203"] is True


def test_parallel_domains_never_feed_cor0203():
    cases = [
        ("ATP_CHALLENGER", "MEN", "SINGLES", "Clay", "ATP_CHALLENGER_MEN_SINGLES_CLAY"),
        ("ATP_MAIN_OR_OTHER", "MEN", "SINGLES", "Hard", "ATP_MAIN_MEN_SINGLES_HARD"),
        ("WTA_MAIN_OR_OTHER", "WOMEN", "SINGLES", "Hard", "WTA_MAIN_WOMEN_SINGLES_HARD"),
        ("ITF_MEN", "MEN", "SINGLES", "I.hard", "ITF_MEN_MEN_SINGLES_HARD"),
        ("ITF_WOMEN", "WOMEN", "SINGLES", "Clay", "ITF_WOMEN_WOMEN_SINGLES_CLAY"),
        ("WTA_CHALLENGER_OR_125", "WOMEN", "DOUBLES", "Grass", "WTA_125_WOMEN_DOUBLES_GRASS"),
    ]
    reg = _registry()
    for circuit, gender, fmt, surface, expected in cases:
        lane = resolve_lane(
            circuit=circuit,
            gender=gender,
            event_format=fmt,
            surface=surface,
            registry=reg,
        )
        assert lane is not None
        assert lane["lane_id"] == expected
        assert lane["status"] in {"RESEARCH_ONLY_NOT_TRAINED", "ACTIVE_PROSPECTIVE_RESEARCH"}
        assert lane["feeds_cor0203"] is False
        assert lane["can_reuse_cor0203_holdout"] is False
        assert lane["can_reuse_cor0203_observations"] is False
        assert not lane["evidence_root"].startswith("evidence/cor0203")
        if lane["status"] == "ACTIVE_PROSPECTIVE_RESEARCH":
            assert lane["holdout"]["holdout_id"] != "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
            assert lane["model_binding"] is not None


def test_unknown_surface_does_not_silently_route():
    lane = resolve_lane(
        circuit="ATP_MAIN",
        gender="MEN",
        event_format="SINGLES",
        surface="Carpet",
        registry=_registry(),
    )
    assert lane is None


def test_parallel_lane_initialization_only_initializes_untrained_lanes(tmp_path):
    reg = _registry()
    expected = sum(
        1 for lane in reg["lanes"]
        if lane["status"] == "RESEARCH_ONLY_NOT_TRAINED"
    )
    result = initialize_lane_states(
        registry=reg,
        out_root=tmp_path / "parallel",
    )
    assert result["initialized_research_lane_count"] == expected
    assert result["existing_cor0203_modified"] is False
    assert result["model_training_performed"] is False
    assert result["holdout_creation_performed"] is False
    assert result["metrics_opened"] is False

    states = list((tmp_path / "parallel").glob("*/state.json"))
    assert len(states) == expected
    for path in states:
        state = json.loads(path.read_text(encoding="utf-8"))
        assert state["status"] == "RESEARCH_ONLY_NOT_TRAINED"
        assert state["historical_dataset_status"] == "NOT_BUILT"
        assert state["candidate_model_status"] == "NOT_TRAINED"
        assert state["holdout_status"] == "NOT_CREATED"
        assert state["prospective_observations"] == 0
        assert state["feeds_cor0203"] is False
        assert state["cor0203_holdout_reuse"] is False
        assert state["cor0203_observation_reuse"] is False
        assert state["metrics_opened"] is False
        assert state["real_money"] == "BLOCKED"
