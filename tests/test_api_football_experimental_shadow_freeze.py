from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from app.research.football.match_analysis_input import (
    FootballHistoryObservation,
    FootballMatchAnalysisInput,
    assess_match_analysis_readiness,
)
from tools.api_football_freeze_experimental_shadow import (
    MODEL_NAME,
    MODEL_ROLE,
    _canonical_hash,
    freeze_experimental_shadow,
)


def _history(fid: int, kickoff: str, team_id: str, opponent_id: str, role: str) -> FootballHistoryObservation:
    if role == "home":
        team_name, opponent_name = f"T{team_id}", f"T{opponent_id}"
    else:
        team_name, opponent_name = f"T{team_id}", f"T{opponent_id}"
    return FootballHistoryObservation(
        fixture_id=str(fid),
        kickoff_utc=kickoff,
        team_id=team_id,
        team_name=team_name,
        opponent_id=opponent_id,
        opponent_name=opponent_name,
        venue_role=role,
        goals_for=2 if fid % 2 == 0 else 1,
        goals_against=1 if fid % 3 else 0,
        competition="Historical League",
        source_provider="api_football",
        observed_at_utc="2026-09-20T00:00:00+00:00",
        source_payload_sha256="b" * 64,
        source_reference=f"test:{fid}",
    )


def _value() -> FootballMatchAnalysisInput:
    home = tuple(
        _history(100 + i, f"2026-09-{10+i:02d}T12:00:00+00:00", "40", str(1000 + i), "home" if i % 2 == 0 else "away")
        for i in range(5)
    )
    away = tuple(
        _history(200 + i, f"2026-09-{10+i:02d}T15:00:00+00:00", "41", str(2000 + i), "away" if i % 2 == 0 else "home")
        for i in range(5)
    )
    return FootballMatchAnalysisInput(
        benchmark_id="TEST_API_FOOTBALL_2026-09-28",
        target_key="api_football:fixture:900",
        fixture_id="900",
        as_of_utc="2026-09-28T06:00:00+00:00",
        kickoff_utc="2026-09-28T18:00:00+00:00",
        home_team_id="40",
        home_team_name="Home FC",
        away_team_id="41",
        away_team_name="Away FC",
        competition_id="39",
        competition_name="League",
        season=2026,
        round_name="R1",
        venue_name="Stadium",
        fixture_source_provider="api_football",
        fixture_payload_sha256="a" * 64,
        fixture_id_namespace="api_football",
        home_team_id_namespace="api_football",
        away_team_id_namespace="api_football",
        home_history=home,
        away_history=away,
    )


def _bundle_and_manifest():
    value = _value()
    row = asdict(value)
    row["canonical_sha256"] = value.canonical_sha256()
    row["readiness"] = asdict(assess_match_analysis_readiness(value))
    bundle = {
        "schema": "MATRIX_API_FOOTBALL_CANONICAL_ANALYSIS_INPUTS_V1",
        "provider": "api_football",
        "analysis_as_of_utc": value.as_of_utc,
        "inputs": [row],
        "blocked_future_inputs": [],
        "not_future_targets": [],
        "protections": {
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    manifest = {
        "status": "PASS",
        "provider": "api_football",
        "analysis_as_of_utc": value.as_of_utc,
        "ready_input_count": 1,
        "bundle_sha256": _canonical_hash(bundle),
        "p_matrix_status": "NOT_GENERATED",
        "baseline_poisson_status": "EXPERIMENTAL_NOT_PROMOTED",
        "real_money": "BLOCKED",
    }
    return bundle, manifest


def test_shadow_freeze_produces_research_only_probabilities_with_at_least_three_markets():
    bundle, manifest = _bundle_and_manifest()
    ledger, adjudication = freeze_experimental_shadow(
        canonical_bundle=bundle,
        canonical_manifest=manifest,
        freeze_at=datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
    )

    assert ledger["frozen_prediction_count"] == 1
    assert ledger["excluded_not_future_count"] == 0
    assert ledger["model_name"] == MODEL_NAME
    assert ledger["model_role"] == MODEL_ROLE
    assert ledger["model_status"] == "EXPERIMENTAL_NOT_PROMOTED"
    assert ledger["p_matrix_status"] == "NOT_GENERATED"
    assert ledger["protections"]["odds_used_to_generate_probability"] is False
    assert ledger["protections"]["outcomes_used_to_generate_probability"] is False
    assert ledger["protections"]["real_money"] == "BLOCKED"

    row = ledger["rows"][0]
    assert row["decision"] == "NO_BET"
    assert row["p_matrix"] is None
    assert row["governed_model_probability"] is None
    assert row["market_count"] == 7
    assert len(row["markets"]) == 7

    assert adjudication["governed_p_matrix_engine_available"] is False
    assert adjudication["promotion_status"] == "BLOCKED"
    assert adjudication["shadow_probability_role"] == "RESEARCH_ONLY_NOT_P_MATRIX"
    assert adjudication["real_money"] == "BLOCKED"


def test_shadow_freeze_excludes_target_that_is_no_longer_future():
    bundle, manifest = _bundle_and_manifest()
    ledger, adjudication = freeze_experimental_shadow(
        canonical_bundle=bundle,
        canonical_manifest=manifest,
        freeze_at=datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc),
    )

    assert ledger["frozen_prediction_count"] == 0
    assert ledger["excluded_not_future_count"] == 1
    assert ledger["excluded_not_future_targets"] == ["api_football:fixture:900"]
    assert adjudication["frozen_shadow_input_count"] == 0


def test_shadow_freeze_rejects_tampered_canonical_input_sha():
    bundle, manifest = _bundle_and_manifest()
    bundle["inputs"][0]["canonical_sha256"] = "0" * 64
    manifest["bundle_sha256"] = _canonical_hash(bundle)

    with pytest.raises(ValueError, match="CANONICAL_INPUT_SHA_MISMATCH"):
        freeze_experimental_shadow(
            canonical_bundle=bundle,
            canonical_manifest=manifest,
            freeze_at=datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
        )
