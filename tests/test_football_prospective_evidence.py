import json

import pytest

from app.application.football.controlled_live_readiness import ControlledLivePolicy
from app.application.football.prospective_evidence import (
    ValidatedMarketEvidence,
    build_prospective_readiness_bundle,
)
from app.research.football.prospective_ledger import (
    ClosingOddsReference,
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
    ProspectivePerformancePolicy,
    ProspectiveSettlement,
)
from scripts.audit_football_prospective_evidence import main


def _validation(**changes):
    payload = dict(
        market_key="over_2_5",
        model_version="football-over25-v1",
        model_state="PAPER_TRADING",
        protected_test_samples=800,
        brier_score=0.18,
        calibration_error=0.03,
        baseline_dominance_confirmed=True,
        walk_forward_folds=8,
        reproducibility_verified=True,
        risk_policy_approved=True,
        kill_switch_verified=True,
        human_approval_required=True,
        compliance_review_complete=True,
        unresolved_p0_count=0,
        evidence_sha256s=("1" * 64, "2" * 64, "3" * 64),
    )
    payload.update(changes)
    return ValidatedMarketEvidence(**payload)


def _populate(ledger, count=8):
    outcomes = [True, True, True, False]
    for index in range(1, count + 1):
        decision = FrozenProspectiveDecision(
            decision_id=f"d-{index}",
            fixture_id=f"f-{index}",
            market_key="over_2_5",
            selection_key="over",
            model_version="football-over25-v1",
            model_probability=0.75,
            decision_at_utc="2026-08-18T17:15:00+00:00",
            fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
            block_id=f"block-{1 + ((index - 1) // 2)}",
            odds_snapshot_sha256="a" * 64,
            odds_observed_at_utc="2026-08-18T17:10:00+00:00",
            decimal_odds=2.0,
            odds_source_provider="licensed_feed",
            odds_source_reference=f"provider://entry/{index}",
            odds_source_authorized=True,
            model_input_sha256s=("b" * 64,),
        )
        ledger.append_decision(decision)
        ledger.append_closing_odds(
            ClosingOddsReference(
                decision_id=decision.decision_id,
                fixture_id=decision.fixture_id,
                market_key=decision.market_key,
                selection_key=decision.selection_key,
                source_provider="licensed_feed",
                source_reference=f"provider://close/{index}",
                observed_at_utc="2026-08-18T18:55:00+00:00",
                fixture_kickoff_utc=decision.fixture_kickoff_utc,
                decimal_odds=1.8,
                source_authorized=True,
            )
        )
        ledger.append_settlement(
            ProspectiveSettlement(
                decision_id=decision.decision_id,
                fixture_id=decision.fixture_id,
                outcome=outcomes[(index - 1) % 4],
                settled_at_utc="2026-08-18T21:30:00+00:00",
                fixture_kickoff_utc=decision.fixture_kickoff_utc,
                result_source_provider="licensed_results",
                result_source_reference=f"provider://result/{index}",
                result_payload_sha256="d" * 64,
            )
        )


def test_builder_derives_counts_and_prospective_flags_from_ledger(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    _populate(ledger, 8)
    bundle = build_prospective_readiness_bundle(
        ledger=ledger,
        validation=_validation(),
        performance_policy=ProspectivePerformancePolicy(
            min_settled_samples=8,
            min_closing_odds_samples=8,
            max_brier_score=0.20,
            max_calibration_error=0.01,
        ),
        controlled_live_policy=ControlledLivePolicy(
            min_protected_test_samples=1,
            max_brier_score=1.0,
            max_calibration_error=1.0,
            min_walk_forward_folds=1,
            min_paper_trading_samples=8,
            min_settled_paper_trading_samples=8,
            min_odds_capture_samples=8,
            min_evidence_artifacts=4,
            min_closing_odds_samples=8,
        ),
        bootstrap_iterations=200,
    )
    evidence = bundle.controlled_live_evidence
    assert evidence.paper_trading_samples == 8
    assert evidence.settled_paper_trading_samples == 8
    assert evidence.closing_odds_samples == 8
    assert evidence.prospective_performance_verified
    assert evidence.positive_clv_confirmed
    assert bundle.readiness.controlled_live_review_eligible
    assert bundle.readiness.automatic_wager_execution_enabled is False


def test_default_gate_remains_blocked_until_real_sample_thresholds_are_met(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    _populate(ledger, 8)
    bundle = build_prospective_readiness_bundle(
        ledger=ledger,
        validation=_validation(),
        bootstrap_iterations=100,
    )
    assert not bundle.readiness.controlled_live_review_eligible
    assert "insufficient_paper_trading" in bundle.readiness.blocked_reasons
    assert "insufficient_closing_odds_capture" in bundle.readiness.blocked_reasons
    assert "prospective_performance_not_verified" in bundle.readiness.blocked_reasons


def test_readiness_is_blocked_when_closing_odds_are_unauthorized(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    decision = FrozenProspectiveDecision(
        decision_id="d-1",
        fixture_id="f-1",
        market_key="over_2_5",
        selection_key="over",
        model_version="football-over25-v1",
        model_probability=0.75,
        decision_at_utc="2026-08-18T17:15:00+00:00",
        fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
        block_id="b-1",
        odds_snapshot_sha256="a" * 64,
        odds_observed_at_utc="2026-08-18T17:10:00+00:00",
        decimal_odds=2.0,
        odds_source_provider="licensed_feed",
        odds_source_reference="provider://entry/1",
        odds_source_authorized=True,
        model_input_sha256s=("b" * 64,),
    )
    ledger.append_decision(decision)
    ledger.append_closing_odds(
        ClosingOddsReference(
            decision_id="d-1",
            fixture_id="f-1",
            market_key="over_2_5",
            selection_key="over",
            source_provider="unapproved_source",
            source_reference="source://close/1",
            observed_at_utc="2026-08-18T18:55:00+00:00",
            fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
            decimal_odds=1.8,
            source_authorized=False,
        )
    )
    ledger.append_settlement(
        ProspectiveSettlement(
            decision_id="d-1",
            fixture_id="f-1",
            outcome=True,
            settled_at_utc="2026-08-18T21:30:00+00:00",
            fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
            result_source_provider="results",
            result_source_reference="result://1",
            result_payload_sha256="d" * 64,
        )
    )
    bundle = build_prospective_readiness_bundle(
        ledger=ledger,
        validation=_validation(),
        performance_policy=ProspectivePerformancePolicy(min_settled_samples=1, min_closing_odds_samples=1),
        bootstrap_iterations=100,
    )
    assert not bundle.controlled_live_evidence.odds_source_authorized
    assert not bundle.controlled_live_evidence.closing_odds_integrity_verified
    assert "odds_source_not_authorized" in bundle.readiness.blocked_reasons


def test_cli_writes_verifiable_blocked_prospective_evidence(tmp_path, capsys):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    _populate(ledger, 4)
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps(_validation().__dict__), encoding="utf-8")
    out_dir = tmp_path / "evidence"
    code = main([
        "--ledger", str(ledger.path),
        "--validation-evidence", str(validation),
        "--evidence-dir", str(out_dir),
    ])
    assert code == 2
    output = capsys.readouterr().out
    assert "MATRIX_FOOTBALL_PROSPECTIVE_STATUS=BLOCKED" in output
    assert "automatic_wager_execution_enabled=False" in output
    artifacts = list(out_dir.glob("football_prospective_readiness_*.json"))
    assert len(artifacts) == 1
    assert (out_dir / f"{artifacts[0].name}.sha256").is_file()
