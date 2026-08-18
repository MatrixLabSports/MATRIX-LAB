from copy import deepcopy
import json

from app.application.football.analysis_runner import (
    build_football_operational_analysis,
    human_summary,
)
from app.research.football.supplemental_history import supplemental_record_sha256
from scripts.run_matrix_football_analysis import main


def _hashed(payload):
    value = dict(payload)
    value["source_record_sha256"] = supplemental_record_sha256(value)
    return value


def _row(day: int, opponent: str, role: str, gf: int, ga: int):
    return _hashed(
        {
            "match_date": f"2026-08-{day:02d}",
            "opponent_name": opponent,
            "venue_role": role,
            "goals_for": gf,
            "goals_against": ga,
            "competition": "League",
            "source_provider": "external_test",
            "source_reference": "https://example.test/source",
            "source_team_id": None,
            "source_opponent_id": None,
            "fixture_identity_kind": "derived",
        }
    )


def _benchmark():
    return {
        "benchmark_id": "operational-b1",
        "benchmark_status": "PARTIAL",
        "provider": "api_football",
        "fixtures": {
            "a_vs_b": {
                "fixture_id": "1",
                "observed_at_utc": "2026-08-18T16:00:00+00:00",
                "kickoff_utc": "2026-08-18T19:00:00+00:00",
                "pre_match_frozen": True,
                "league": {"id": "2", "name": "Cup", "season": 2026, "round": "PO"},
                "home": {"id": "10", "name": "A"},
                "away": {"id": "20", "name": "B"},
                "venue": {"name": "S"},
                "source_payload_sha256": "d" * 64,
            }
        },
        "histories": {"a_vs_b": {}},
        "unresolved_targets": [],
    }


def _supplement(history_count: int = 5):
    days = list(range(13, 13 - history_count, -1))
    histories = {
        "home": [_row(day, f"H{day}", "home", 2, 1) for day in days],
        "away": [_row(day, f"A{day}", "away", 1, 1) for day in days],
    }
    return {
        "benchmark_id": "operational-b1",
        "captured_at_utc": "2026-08-18T17:00:00+00:00",
        "methodology": {
            "money_decisions_enabled": False,
            "source_equivalence_assumed": False,
        },
        "targets": {"a_vs_b": {"histories": histories}},
    }


def test_operational_analysis_is_functional_but_fail_closed_for_money():
    result = build_football_operational_analysis(_benchmark(), supplement=_supplement())
    assert result.passed is True
    assert result.resolved_input_count == 1
    assert result.ready_for_experimental_evaluation_count == 1
    assert result.money_decisions_enabled is False
    assert result.analysis_mode == "EXPERIMENTAL_RESEARCH_ONLY"
    evaluation = result.experimental_evaluations[0]
    assert evaluation["decision"] == "NO_BET"
    assert evaluation["model_status"] == "EXPERIMENTAL_NOT_PROMOTED"
    assert evaluation["probabilities"] is not None


def test_operational_analysis_blocks_when_history_is_below_minimum():
    result = build_football_operational_analysis(_benchmark(), supplement=_supplement(history_count=4))
    assert result.passed is False
    assert result.ready_for_experimental_evaluation_count == 0
    assert result.experimental_evaluations[0]["decision"] == "NO_BET"
    assert result.experimental_evaluations[0]["model_status"] == "BLOCKED_INSUFFICIENT_DATA"


def test_summary_labels_probabilities_diagnostic_only():
    result = build_football_operational_analysis(_benchmark(), supplement=_supplement())
    report = human_summary(result)
    assert "READY_FOR_EXPERIMENTAL_REVIEW" in report
    assert "money_decisions_enabled=False" in report
    assert "DIAGNOSTIC_ONLY" in report
    assert "decision=NO_BET" in report


def test_cli_writes_verifiable_evidence_and_returns_zero(tmp_path, capsys):
    benchmark = tmp_path / "benchmark.json"
    supplement = tmp_path / "supplement.json"
    evidence_dir = tmp_path / "evidence"
    benchmark.write_text(json.dumps(_benchmark()), encoding="utf-8")
    supplement.write_text(json.dumps(_supplement()), encoding="utf-8")

    exit_code = main(
        [
            "--benchmark",
            str(benchmark),
            "--supplement",
            str(supplement),
            "--evidence-dir",
            str(evidence_dir),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "MATRIX_FOOTBALL_OPERATIONAL_STATUS=READY_FOR_EXPERIMENTAL_REVIEW" in output
    evidence_files = list(evidence_dir.glob("football_match_analysis_*.json"))
    assert len(evidence_files) == 1
    assert (evidence_dir / f"{evidence_files[0].name}.sha256").is_file()


def test_cli_returns_blocked_exit_code_for_insufficient_history(tmp_path):
    benchmark = tmp_path / "benchmark.json"
    supplement = tmp_path / "supplement.json"
    benchmark.write_text(json.dumps(_benchmark()), encoding="utf-8")
    supplement.write_text(json.dumps(_supplement(history_count=3)), encoding="utf-8")

    exit_code = main(
        [
            "--benchmark",
            str(benchmark),
            "--supplement",
            str(supplement),
            "--evidence-dir",
            str(tmp_path / "evidence"),
        ]
    )
    assert exit_code == 2


def test_source_equivalence_flag_is_preserved_as_a_warning_fact_not_permission():
    supplement = deepcopy(_supplement())
    supplement["methodology"]["source_equivalence_assumed"] = True
    result = build_football_operational_analysis(_benchmark(), supplement=supplement)
    assert result.source_equivalence_assumed is True
    assert result.money_decisions_enabled is False
