from datetime import datetime, timedelta, timezone

import pytest

from app.application.football.real_money_risk import (
    FootballCapitalState,
    FootballHumanApproval,
    FootballRiskGateInput,
    FootballRiskPolicy,
    FootballWagerCandidate,
    assess_football_real_money_risk,
    candidate_fingerprint,
    full_kelly_fraction,
    risk_policy_evidence_flags,
)

NOW = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def candidate(**changes):
    data = dict(
        fixture_id="fixture-1",
        market_key="match_result_home",
        selection_key="home",
        model_version="football-model-1",
        model_probability=0.60,
        decimal_odds=2.00,
        quoted_at=NOW - timedelta(seconds=2),
        evaluated_at=NOW,
        phase="PREMATCH",
        evidence_sha256=SHA,
        recovery_or_martingale_flag=False,
    )
    data.update(changes)
    return FootballWagerCandidate(**data)


def capital(**changes):
    data = dict(
        bankroll=1000.0,
        day_start_bankroll=1000.0,
        peak_bankroll=1000.0,
        daily_exposure=0.0,
        market_exposure=0.0,
        total_open_exposure=0.0,
    )
    data.update(changes)
    return FootballCapitalState(**data)


def base_input(**changes):
    c = changes.pop("candidate", candidate())
    cap = changes.pop("capital", capital())
    data = dict(
        candidate=c,
        capital=cap,
        controlled_live_review_eligible=True,
        odds_source_authorized=True,
        data_quality_passed=True,
        compliance_review_complete=True,
        kill_switch_manual_active=False,
        assessed_at=NOW + timedelta(seconds=2),
        approval=None,
    )
    data.update(changes)
    return FootballRiskGateInput(**data)


def approval_for(c, stake, *, approved_at=None, expires_at=None):
    approved_at = approved_at or (NOW + timedelta(seconds=1))
    expires_at = expires_at or (NOW + timedelta(seconds=20))
    return FootballHumanApproval(
        approval_id="approval-1",
        candidate_fingerprint=candidate_fingerprint(c, stake),
        approved_stake=stake,
        approved_at=approved_at,
        expires_at=expires_at,
        approver="human-operator",
    )


def test_full_kelly_fraction_is_correct_and_never_negative():
    assert full_kelly_fraction(0.60, 2.0) == pytest.approx(0.20)
    assert full_kelly_fraction(0.40, 2.0) == 0.0


def test_default_policy_caps_fractional_kelly_to_half_percent_bankroll():
    decision = assess_football_real_money_risk(base_input())
    assert decision.full_kelly_fraction == pytest.approx(0.20)
    assert decision.policy_kelly_fraction == pytest.approx(0.005)
    assert decision.suggested_stake == 5.0
    assert decision.hard_stake_cap == 5.0
    assert decision.approved_for_human_submission is False
    assert "human_approval_missing" in decision.blocked_reasons


def test_valid_exact_human_approval_can_clear_risk_gate_but_never_auto_execute():
    c = candidate()
    first = assess_football_real_money_risk(base_input(candidate=c))
    approval = approval_for(c, first.suggested_stake)
    decision = assess_football_real_money_risk(base_input(candidate=c, approval=approval))
    assert decision.status == "HUMAN_SUBMISSION_APPROVED"
    assert decision.approved_for_human_submission is True
    assert decision.automatic_wager_execution_enabled is False
    assert decision.blocked_reasons == ()


def test_controlled_live_gate_must_pass():
    decision = assess_football_real_money_risk(base_input(controlled_live_review_eligible=False))
    assert "controlled_live_evidence_gate_blocked" in decision.blocked_reasons


def test_unauthorized_odds_source_blocks():
    decision = assess_football_real_money_risk(base_input(odds_source_authorized=False))
    assert "odds_source_not_authorized" in decision.blocked_reasons


def test_bad_data_quality_blocks():
    decision = assess_football_real_money_risk(base_input(data_quality_passed=False))
    assert "data_quality_gate_failed" in decision.blocked_reasons


def test_compliance_review_is_mandatory():
    decision = assess_football_real_money_risk(base_input(compliance_review_complete=False))
    assert "compliance_review_incomplete" in decision.blocked_reasons


def test_manual_kill_switch_blocks():
    decision = assess_football_real_money_risk(base_input(kill_switch_manual_active=True))
    assert "manual_kill_switch_active" in decision.blocked_reasons


def test_martingale_or_loss_recovery_is_forbidden():
    decision = assess_football_real_money_risk(base_input(candidate=candidate(recovery_or_martingale_flag=True)))
    assert "loss_recovery_or_martingale_forbidden" in decision.blocked_reasons


def test_stale_prematch_quote_blocks():
    c = candidate(quoted_at=NOW - timedelta(seconds=31))
    decision = assess_football_real_money_risk(base_input(candidate=c))
    assert "odds_quote_stale" in decision.blocked_reasons


def test_live_quote_has_stricter_freshness_limit():
    c = candidate(phase="LIVE", quoted_at=NOW - timedelta(seconds=6))
    decision = assess_football_real_money_risk(base_input(candidate=c))
    assert "odds_quote_stale" in decision.blocked_reasons


def test_odds_outside_governed_range_blocks():
    decision = assess_football_real_money_risk(base_input(candidate=candidate(decimal_odds=8.0)))
    assert "odds_outside_governed_range" in decision.blocked_reasons


def test_daily_drawdown_kill_switch_blocks_at_threshold():
    cap = capital(bankroll=970.0, day_start_bankroll=1000.0, peak_bankroll=1000.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert "daily_drawdown_kill_switch" in decision.blocked_reasons


def test_peak_drawdown_kill_switch_blocks_at_threshold():
    cap = capital(bankroll=920.0, day_start_bankroll=920.0, peak_bankroll=1000.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert "peak_drawdown_kill_switch" in decision.blocked_reasons


def test_non_positive_edge_blocks():
    decision = assess_football_real_money_risk(base_input(candidate=candidate(model_probability=0.49, decimal_odds=2.0)))
    assert "non_positive_model_edge" in decision.blocked_reasons


def test_daily_exposure_cap_blocks_when_exhausted():
    cap = capital(daily_exposure=20.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert "exposure_limit_reached" in decision.blocked_reasons


def test_market_exposure_cap_blocks_when_exhausted():
    cap = capital(market_exposure=10.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert "exposure_limit_reached" in decision.blocked_reasons


def test_total_open_exposure_cap_blocks_when_exhausted():
    cap = capital(total_open_exposure=20.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert "exposure_limit_reached" in decision.blocked_reasons


def test_exposure_capacity_reduces_suggested_stake():
    cap = capital(daily_exposure=18.0)
    decision = assess_football_real_money_risk(base_input(capital=cap))
    assert decision.suggested_stake == 2.0


def test_approval_must_match_exact_candidate_and_stake():
    c = candidate()
    wrong = candidate(selection_key="away")
    approval = approval_for(wrong, 5.0)
    decision = assess_football_real_money_risk(base_input(candidate=c, approval=approval))
    assert "human_approval_candidate_mismatch" in decision.blocked_reasons


def test_expired_approval_blocks():
    c = candidate()
    approval = approval_for(
        c,
        5.0,
        approved_at=NOW + timedelta(milliseconds=500),
        expires_at=NOW + timedelta(milliseconds=1500),
    )
    decision = assess_football_real_money_risk(base_input(candidate=c, approval=approval))
    assert "human_approval_expired" in decision.blocked_reasons


def test_approval_ttl_cannot_exceed_policy():
    c = candidate()
    approval = approval_for(
        c,
        5.0,
        approved_at=NOW + timedelta(seconds=1),
        expires_at=NOW + timedelta(seconds=61),
    )
    decision = assess_football_real_money_risk(base_input(candidate=c, approval=approval))
    assert "human_approval_ttl_exceeds_policy" in decision.blocked_reasons


def test_approval_above_hard_cap_blocks_even_if_fingerprint_matches():
    c = candidate()
    approval = approval_for(c, 6.0)
    decision = assess_football_real_money_risk(base_input(candidate=c, approval=approval))
    assert "human_approval_stake_above_hard_cap" in decision.blocked_reasons


def test_risk_policy_evidence_flags_are_fail_closed():
    decision = assess_football_real_money_risk(base_input())
    flags = risk_policy_evidence_flags(decision)
    assert flags["risk_policy_approved"] is False
    assert flags["kill_switch_verified"] is True
    assert flags["human_approval_required"] is True


def test_policy_rejects_aggressive_fractional_kelly():
    with pytest.raises(ValueError, match="fractional_kelly"):
        FootballRiskPolicy(fractional_kelly=0.75)


def test_candidate_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        candidate(evaluated_at=datetime(2026, 8, 18, 19, 0))


def test_candidate_rejects_invalid_sha():
    with pytest.raises(ValueError, match="SHA-256"):
        candidate(evidence_sha256="bad")


def test_consumed_approval_id_is_blocked_as_replay():
    c = candidate()
    approval = approval_for(c, 5.0)
    gate = base_input(candidate=c, approval=approval, consumed_approval_ids=frozenset({approval.approval_id}))
    decision = assess_football_real_money_risk(gate)
    assert "human_approval_replay_detected" in decision.blocked_reasons


def test_risk_policy_audit_approves_conservative_defaults():
    from app.application.football.real_money_risk import audit_football_risk_policy

    audit = audit_football_risk_policy()
    assert audit.passed is True
    assert audit.risk_policy_approved is True
    assert audit.kill_switch_verified is True
    assert audit.human_approval_required is True
    assert audit.automatic_wager_execution_enabled is False


def test_risk_policy_audit_rejects_loose_daily_exposure():
    from app.application.football.real_money_risk import audit_football_risk_policy

    policy = FootballRiskPolicy(max_daily_exposure_fraction_bankroll=0.06)
    audit = audit_football_risk_policy(policy)
    assert audit.passed is False
    assert "daily_exposure_cap_above_five_percent" in audit.blocked_reasons
