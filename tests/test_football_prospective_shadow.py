from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from app.research.football.prospective_shadow import (
    FootballProspectiveShadowLedger,
    FootballShadowOutcome,
    freeze_football_operational_analysis,
)
from app.research.football.supplemental_history import supplemental_record_sha256


UTC = timezone.utc


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
        "benchmark_id": "shadow-b1",
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
    return {
        "benchmark_id": "shadow-b1",
        "captured_at_utc": "2026-08-18T17:00:00+00:00",
        "methodology": {
            "money_decisions_enabled": False,
            "source_equivalence_assumed": False,
        },
        "targets": {
            "a_vs_b": {
                "histories": {
                    "home": [_row(day, f"H{day}", "home", 2, 1) for day in days],
                    "away": [_row(day, f"A{day}", "away", 1, 1) for day in days],
                }
            }
        },
    }


def test_freezes_existing_matrix_probabilities_before_kickoff(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    result = freeze_football_operational_analysis(
        _benchmark(),
        supplement=_supplement(),
        ledger=ledger,
        batch_id="batch-1",
        repository_head="a" * 40,
        frozen_at_utc=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
    )
    assert result.prediction_count == 1
    assert result.money_decisions_enabled is False
    assert result.official_paper_trading is False
    events = ledger.load_events()
    assert len(events) == 1
    assert events[0].event_type == "PREDICTION_FROZEN"
    probability = events[0].payload["probabilities"]["home_win"]
    assert 0.0 <= probability <= 1.0


def test_freeze_fails_closed_at_or_after_kickoff(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    with pytest.raises(ValueError, match="PROSPECTIVE_FREEZE_TOO_LATE"):
        freeze_football_operational_analysis(
            _benchmark(),
            supplement=_supplement(),
            ledger=ledger,
            batch_id="batch-1",
            repository_head="a" * 40,
            frozen_at_utc=datetime(2026, 8, 18, 19, 0, tzinfo=UTC),
        )
    assert not ledger.path.exists()


def test_insufficient_history_never_writes_prediction(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    with pytest.raises(ValueError, match="FOOTBALL_OPERATIONAL_ANALYSIS_NOT_READY"):
        freeze_football_operational_analysis(
            _benchmark(),
            supplement=_supplement(history_count=4),
            ledger=ledger,
            batch_id="batch-1",
            repository_head="a" * 40,
            frozen_at_utc=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
        )
    assert not ledger.path.exists()


def test_duplicate_fixture_model_batch_is_rejected(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    kwargs = dict(
        benchmark=_benchmark(),
        supplement=_supplement(),
        ledger=ledger,
        batch_id="batch-1",
        repository_head="a" * 40,
        frozen_at_utc=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
    )
    freeze_football_operational_analysis(**kwargs)
    with pytest.raises(ValueError, match="duplicate fixture-model-batch"):
        freeze_football_operational_analysis(**kwargs)


def test_outcome_enables_calibration_metrics(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    freeze_football_operational_analysis(
        _benchmark(),
        supplement=_supplement(),
        ledger=ledger,
        batch_id="batch-1",
        repository_head="a" * 40,
        frozen_at_utc=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
    )
    event = ledger.load_events()[0]
    prediction_id = event.payload["prediction_id"]
    evidence = sha256(b"final score source").hexdigest()
    ledger.append_outcome(
        FootballShadowOutcome(
            outcome_id="outcome-1",
            prediction_id=prediction_id,
            fixture_id="1",
            fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
            home_goals=2,
            away_goals=1,
            settled_at_utc="2026-08-18T21:00:00+00:00",
            source_provider="test-result-source",
            source_reference="result://1",
            source_evidence_sha256=evidence,
        )
    )
    performance = ledger.performance(model_version="transparent_poisson_baseline_v1")
    assert performance.settled_predictions == 1
    assert performance.multiclass_brier is not None
    assert performance.multiclass_log_loss is not None
    assert performance.over_2_5_brier is not None


def test_ledger_hash_chain_tamper_is_detected(tmp_path):
    ledger = FootballProspectiveShadowLedger(tmp_path / "shadow.jsonl")
    freeze_football_operational_analysis(
        _benchmark(),
        supplement=_supplement(),
        ledger=ledger,
        batch_id="batch-1",
        repository_head="a" * 40,
        frozen_at_utc=datetime(2026, 8, 18, 18, 0, tzinfo=UTC),
    )
    raw = ledger.path.read_text(encoding="utf-8")
    ledger.path.write_text(raw.replace('"home_win":', '"home_win":0.999,"tampered":'), encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        ledger.audit()


def test_cli_freezes_to_explicit_external_paths(tmp_path, monkeypatch, capsys):
    from scripts import run_matrix_football_prospective_shadow as cli

    benchmark_path = tmp_path / "benchmark.json"
    supplement_path = tmp_path / "supplement.json"
    ledger_path = tmp_path / "shadow.jsonl"
    result_path = tmp_path / "result.json"
    benchmark_path.write_text(json.dumps(_benchmark()), encoding="utf-8")
    supplement_path.write_text(json.dumps(_supplement()), encoding="utf-8")

    def fake_git(*args):
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_git", fake_git)
    monkeypatch.setattr(
        "app.research.football.prospective_shadow.datetime",
        type(
            "FrozenDateTime",
            (),
            {
                "now": staticmethod(
                    lambda tz=None: datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
                ),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            },
        ),
    )

    code = cli.main(
        [
            "--benchmark",
            str(benchmark_path),
            "--supplement",
            str(supplement_path),
            "--batch-id",
            "batch-cli",
            "--ledger",
            str(ledger_path),
            "--result-json",
            str(result_path),
        ]
    )
    assert code == 0
    assert ledger_path.is_file()
    assert result_path.is_file()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["analysis_mode"] == "PRE_FREEZE_PROSPECTIVE_SHADOW"
    assert payload["money_decisions_enabled"] is False
    assert payload["benchmark_file_sha256"] == sha256(benchmark_path.read_bytes()).hexdigest()
    assert payload["supplement_file_sha256"] == sha256(supplement_path.read_bytes()).hexdigest()
    assert "MATRIX_FOOTBALL_PROSPECTIVE_SHADOW=PASS" in capsys.readouterr().out
