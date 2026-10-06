from __future__ import annotations

import json
from pathlib import Path


POLICY = Path("docs/providers/MATRIX_AUXILIARY_PIT_FEATURE_SOURCES_V1.json")
EVIDENCE = Path(
    "evidence/governance/"
    "MATRIX_AUXILIARY_SOURCE_BROWSER_VERIFICATION_20261004.json"
)


def test_auxiliary_feature_sources_are_pit_governed_and_fail_closed():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    rules = policy["admission_rules"]

    assert policy["status"] == "ACTIVE_PERMANENT_ADDITIVE"
    assert rules["point_in_time_required"] is True
    assert rules["captured_at_required"] is True
    assert rules["source_url_or_entity_reference_required"] is True
    assert rules["raw_snapshot_or_physical_evidence_required"] is True
    assert rules["canonical_identity_required"] is True
    assert rules["missing_not_zero"] is True
    assert rules["silent_imputation"] is False
    assert rules["name_only_identity_join"] is False
    assert rules["future_knowledge_used"] is False
    assert rules["historical_backfill_allowed"] is False
    assert rules["odds_to_p_matrix"] is False
    assert rules["automatic_model_feed"] is False
    assert rules["automatic_model_promotion"] is False
    assert rules["automatic_wagering"] is False
    assert rules["real_money"] == "BLOCKED"

    assert (
        policy["provider_priority_rule"]["no_single_source_world_truth"]
        is True
    )
    assert (
        policy["provider_priority_rule"]["no_single_source_feature_override"]
        is True
    )

    daily = policy["daily_crosscheck_rule"]
    assert daily["required"] is True
    assert set(daily["sports"]) == {"tennis", "football"}
    assert "sofascore" in daily["tennis_required_sources"]
    assert "flashscore" in daily["tennis_required_sources"]
    assert "rapidapi_tennis" in daily["tennis_required_sources"]
    assert "api_tennis" in daily["tennis_required_sources"]
    assert "sofascore" in daily["football_required_sources"]
    assert "flashscore" in daily["football_required_sources"]
    assert "api_football" in daily["football_required_sources"]
    assert daily["fail_closed_if_browser_crosscheck_missing"] is True
    assert daily["no_single_source_world_truth"] is True

    order = policy["calendar_first_operating_order"]
    assert order["required"] is True
    assert set(order["applies_to"]) == {"tennis", "football"}
    assert order["order"][0] == "1_SOFASCORE_AND_FLASHSCORE_WORLD_CALENDAR_BASELINE"
    assert order["order"][1] == "2_PAID_APIS_STRUCTURED_ACQUISITION_AND_ENRICHMENT"
    assert order["daily_count_report_required"] is True
    assert order["invented_counts_prohibited"] is True
    assert order["api_must_not_run_as_world_truth_before_browser_baseline"] is True


def test_browser_verification_physically_confirms_requested_capabilities():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["status"] == "PASS"
    assert "visible ATP/WTA rankings" in evidence["sofascore"]["tennis"]["verified"]
    assert "ranking history" in evidence["flashscore"]["tennis"]["verified"]
    assert "player statistics" in evidence["sofascore"]["football"]["verified"]
    assert "expected goals xG" in evidence["flashscore"]["football"]["verified"]
    assert "lineups" in evidence["flashscore"]["football"]["verified"]
    assert evidence["protections"]["historical_backfill_allowed"] is False
    assert evidence["protections"]["automatic_model_feed"] is False
