import json

import pytest

from app.application.football.controlled_live_readiness import (
    ControlledLiveEvidence,
    ControlledLivePolicy,
    assess_controlled_live_readiness,
    human_summary,
)
from scripts.audit_football_controlled_live_readiness import main


def _evidence(**changes):
    payload = dict(
        market_key="over_2_5",
        model_version="football-over25-v1",
        model_state="PAPER_TRADING",
        protected_test_samples=800,
        brier_score=0.18,
        calibration_error=0.03,
        baseline_dominance_confirmed=True,
        walk_forward_folds=8,
        paper_trading_samples=700,
        settled_paper_trading_samples=650,
        odds_capture_samples=900,
        odds_source_authorized=True,
        odds_timestamp_integrity_verified=True,
        reproducibility_verified=True,
        risk_policy_approved=True,
        kill_switch_verified=True,
        human_approval_required=True,
        compliance_review_complete=True,
        unresolved_p0_count=0,
        evidence_sha256s=("a" * 64, "b" * 64, "c" * 64, "d" * 64),
        closing_odds_samples=500,
        closing_odds_integrity_verified=True,
        prospective_performance_verified=True,
        positive_clv_confirmed=True,
    )
    payload.update(changes)
    return ControlledLiveEvidence(**payload)


def test_gate_can_reach_controlled_review_only_when_every_gate_passes():
    result = assess_controlled_live_readiness(_evidence())
    assert result.status == "CONTROLLED_LIVE_REVIEW_ELIGIBLE"
    assert result.controlled_live_review_eligible is True
    assert result.automatic_wager_execution_enabled is False
    assert result.human_approval_required is True
    assert result.blocked_reasons == ()


def test_gate_is_fail_closed_for_current_experimental_state():
    result = assess_controlled_live_readiness(
        _evidence(
            model_state="BACKTESTED",
            protected_test_samples=0,
            brier_score=None,
            calibration_error=None,
            baseline_dominance_confirmed=False,
            walk_forward_folds=0,
            paper_trading_samples=0,
            settled_paper_trading_samples=0,
            odds_capture_samples=0,
            odds_source_authorized=False,
            odds_timestamp_integrity_verified=False,
            reproducibility_verified=False,
            risk_policy_approved=False,
            kill_switch_verified=False,
            compliance_review_complete=False,
            unresolved_p0_count=4,
            evidence_sha256s=(),
        )
    )
    assert result.status == "BLOCKED"
    assert result.controlled_live_review_eligible is False
    assert result.automatic_wager_execution_enabled is False
    assert "insufficient_paper_trading" in result.blocked_reasons
    assert "odds_source_not_authorized" in result.blocked_reasons
    assert "unresolved_p0_items" in result.blocked_reasons


def test_human_approval_gate_is_non_optional():
    result = assess_controlled_live_readiness(_evidence(human_approval_required=False))
    assert "human_approval_gate_missing" in result.blocked_reasons
    assert not result.controlled_live_review_eligible


def test_one_market_cannot_be_promoted_by_unnamed_or_invalid_evidence():
    with pytest.raises(ValueError, match="market_key"):
        _evidence(market_key=" ")
    with pytest.raises(ValueError, match="SHA-256"):
        _evidence(evidence_sha256s=("not-a-hash",))


def test_policy_rejects_incoherent_settled_minimum():
    with pytest.raises(ValueError, match="settled"):
        ControlledLivePolicy(min_paper_trading_samples=100, min_settled_paper_trading_samples=101)


def test_cli_writes_verifiable_blocked_evidence(tmp_path, capsys):
    evidence = _evidence(
        model_state="BACKTESTED",
        paper_trading_samples=0,
        settled_paper_trading_samples=0,
    )
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps(evidence.__dict__), encoding="utf-8")
    out_dir = tmp_path / "evidence"
    code = main(["--evidence", str(payload), "--evidence-dir", str(out_dir)])
    assert code == 2
    output = capsys.readouterr().out
    assert "MATRIX_FOOTBALL_CONTROLLED_LIVE_STATUS=BLOCKED" in output
    artifacts = list(out_dir.glob("football_controlled_live_readiness_*.json"))
    assert len(artifacts) == 1
    assert (out_dir / f"{artifacts[0].name}.sha256").is_file()


def test_cli_returns_zero_only_for_controlled_review_eligibility(tmp_path, capsys):
    evidence = _evidence()
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps(evidence.__dict__), encoding="utf-8")
    code = main(["--evidence", str(payload), "--evidence-dir", str(tmp_path / "evidence")])
    assert code == 0
    output = capsys.readouterr().out
    assert "CONTROLLED_LIVE_REVIEW_ELIGIBLE" in output
    assert "automatic_wager_execution_enabled=False" in output


def test_summary_never_claims_automatic_execution():
    summary = human_summary(assess_controlled_live_readiness(_evidence()))
    assert "automatic_wager_execution_enabled=False" in summary
    assert "human_approval_required=True" in summary
