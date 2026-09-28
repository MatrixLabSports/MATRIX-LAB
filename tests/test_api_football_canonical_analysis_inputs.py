from datetime import datetime, timezone

import pytest

from app.research.football.match_analysis_input import build_match_analysis_inputs_from_benchmark
from tools.api_football_canonicalize_analysis_inputs import build_canonical_analysis_bundle


def _history(fid: int, when: str, focal: str, opponent: str, focal_home: bool) -> dict:
    if focal_home:
        home_id, away_id = focal, opponent
        home_name, away_name = f"T{focal}", f"T{opponent}"
        home_goals, away_goals = 2, 1
    else:
        home_id, away_id = opponent, focal
        home_name, away_name = f"T{opponent}", f"T{focal}"
        home_goals, away_goals = 0, 1
    return {
        "fixture_id": str(fid),
        "kickoff_utc": when,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": home_name,
        "away_team": away_name,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "competition": "Historical League",
        "source_payload_sha256": "b" * 64,
        "source_reference": f"test:{fid}",
    }


def _benchmark() -> dict:
    target = "api_football:fixture:900"
    home_rows = [
        _history(100 + i, f"2026-09-{10+i:02d}T12:00:00+00:00", "40", str(1000 + i), i % 2 == 0)
        for i in range(5)
    ]
    away_rows = [
        _history(200 + i, f"2026-09-{10+i:02d}T15:00:00+00:00", "41", str(2000 + i), i % 2 == 1)
        for i in range(5)
    ]
    return {
        "benchmark_id": "TEST_API_FOOTBALL_2026-09-28",
        "provider": "api_football",
        "captured_at_utc": "2026-09-28T04:00:00+00:00",
        "money_decisions_enabled": False,
        "analysis_mode": "PREMATCH_RESEARCH_ONLY",
        "real_money": "BLOCKED",
        "fixtures": {
            target: {
                "fixture_id": "900",
                "observed_at_utc": "2026-09-28T04:00:00+00:00",
                "kickoff_utc": "2026-09-28T18:00:00+00:00",
                "pre_match_frozen": True,
                "league": {"id": "39", "name": "League", "season": 2026, "round": "R1"},
                "home": {"id": "40", "name": "Home FC"},
                "away": {"id": "41", "name": "Away FC"},
                "venue": {"id": "1", "name": "Stadium"},
                "source_payload_sha256": "a" * 64,
            }
        },
        "histories": {
            target: {
                "home": {
                    "team_id": "40",
                    "team_name": "Home FC",
                    "observed_at_utc": "2026-09-28T05:00:00+00:00",
                    "completed_before_target": home_rows,
                    "history_count": 5,
                },
                "away": {
                    "team_id": "41",
                    "team_name": "Away FC",
                    "observed_at_utc": "2026-09-28T05:00:00+00:00",
                    "completed_before_target": away_rows,
                    "history_count": 5,
                },
            }
        },
        "unresolved_targets": [],
    }


def test_runtime_analysis_as_of_accepts_history_captured_after_fixture_discovery():
    benchmark = _benchmark()

    with pytest.raises(ValueError, match="observed after analysis as_of"):
        build_match_analysis_inputs_from_benchmark(benchmark)

    values, rejected = build_match_analysis_inputs_from_benchmark(
        benchmark,
        analysis_as_of_utc="2026-09-28T06:00:00+00:00",
    )
    assert rejected == ()
    assert len(values) == 1
    assert values[0].as_of_utc == "2026-09-28T06:00:00+00:00"
    assert len(values[0].home_history) == 5
    assert len(values[0].away_history) == 5


def test_canonical_bundle_emits_only_pit_ready_inputs_and_never_generates_probability():
    bundle, manifest = build_canonical_analysis_bundle(
        benchmark=_benchmark(),
        analysis_as_of=datetime(2026, 9, 28, 6, 0, tzinfo=timezone.utc),
    )

    assert manifest["status"] == "PASS"
    assert manifest["ready_input_count"] == 1
    assert manifest["blocked_future_input_count"] == 0
    assert manifest["not_future_at_analysis_count"] == 0
    assert manifest["p_matrix_status"] == "NOT_GENERATED"
    assert manifest["baseline_poisson_status"] == "EXPERIMENTAL_NOT_PROMOTED"
    assert manifest["odds_used_to_generate_model_probability"] is False
    assert manifest["real_money"] == "BLOCKED"

    row = bundle["inputs"][0]
    assert row["as_of_utc"] == "2026-09-28T06:00:00+00:00"
    assert row["readiness"]["status"] == "READY_FOR_EXPERIMENTAL_EVALUATION"
    assert row["canonical_sha256"]
    assert bundle["protections"]["model_probability_generated"] is False


def test_canonical_bundle_fail_closed_excludes_fixture_at_or_after_kickoff():
    bundle, manifest = build_canonical_analysis_bundle(
        benchmark=_benchmark(),
        analysis_as_of=datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc),
    )

    assert manifest["ready_input_count"] == 0
    assert manifest["builder_output_count"] == 0
    assert manifest["not_future_at_analysis_count"] == 1
    assert manifest["rejected_target_count"] == 1
    assert bundle["not_future_targets"] == ["api_football:fixture:900"]
