from datetime import datetime, timedelta, timezone

import pytest

from app.security.provider_failover import (
    FailoverDrillAssessment,
    FailoverDrillEvidence,
    FailoverDrillStatus,
    evaluate_failover_drill,
)
from app.security.provider_operational import (
    ProviderOperationalAssessment,
    ProviderOperationalObservation,
    ProviderOperationalProfile,
    ProviderOperationalStatus,
    ProviderRole,
    evaluate_provider_operational,
)
from app.security.provider_portfolio import (
    PortfolioStatus,
    ProviderCandidate,
    ProviderPortfolioAssessment,
    ProviderPortfolioPlan,
    choose_failover_candidate,
    evaluate_provider_portfolio,
)
from app.security.provider_portfolio_gate import (
    ProviderPortfolioGateResult,
    ProviderPortfolioGateStatus,
    evaluate_provider_portfolio_gate,
)
from app.security.provider_rights import ProviderRightsAssessment, ProviderRightsStatus

NOW = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)
SHA = "a" * 64
SHA2 = "b" * 64


def op_profile(**kwargs):
    values = dict(
        provider_id="provider-a",
        profile_version="1.0",
        role=ProviderRole.PRIMARY,
        availability_slo_bps=9900,
        max_p95_latency_ms=500,
        max_p99_latency_ms=900,
        max_p95_freshness_seconds=60,
        min_coverage_bps=9500,
        min_quality_score_bps=9500,
        min_stable_id_rate_bps=9900,
        max_error_rate_bps=100,
        max_quota_utilization_bps=9000,
        min_quota_reserve_units=100,
        monthly_budget_cents=100000,
        max_projected_budget_utilization_bps=9000,
        observation_max_age_minutes=30,
    )
    values.update(kwargs)
    return ProviderOperationalProfile(**values)


def op_obs(profile=None, **kwargs):
    profile = profile or op_profile()
    values = dict(
        observation_id="obs-1",
        provider_id=profile.provider_id,
        profile_fingerprint=profile.fingerprint,
        observed_at=NOW - timedelta(minutes=5),
        window_start=NOW - timedelta(hours=1),
        window_end=NOW - timedelta(minutes=10),
        availability_bps=10000,
        p95_latency_ms=300,
        p99_latency_ms=600,
        p95_freshness_seconds=25,
        coverage_bps=9900,
        quality_score_bps=9800,
        stable_id_rate_bps=10000,
        error_rate_bps=20,
        quota_limit_units=10000,
        quota_remaining_units=5000,
        expected_units_next_window=500,
        current_month_cost_cents=35000,
        projected_month_cost_cents=70000,
        provider_incident_open=False,
        provider_degraded=False,
    )
    values.update(kwargs)
    return ProviderOperationalObservation(**values)


def rights(status=ProviderRightsStatus.PASS):
    return ProviderRightsAssessment(status=status, reasons=(), profile_fingerprint=SHA, evidence_fingerprint=SHA2)


def operational(status=ProviderOperationalStatus.PASS):
    return ProviderOperationalAssessment(status=status, reasons=(), profile_fingerprint=SHA, observation_fingerprint=SHA2)


def candidate(provider_id, role, *, status=ProviderOperationalStatus.PASS, rights_status=ProviderRightsStatus.PASS, group=None, priority=1):
    return ProviderCandidate(
        provider_id=provider_id,
        role=role,
        rights=rights(rights_status),
        operational=operational(status),
        independence_group=group or provider_id,
        priority=priority,
    )


def plan(**kwargs):
    values = dict(
        plan_id="portfolio-1",
        sport="football",
        market_or_dataset="prematch-odds",
        primary_provider_id="provider-a",
        fallback_provider_ids=("provider-b",),
        reference_provider_ids=("provider-c",),
        created_at=NOW,
        human_approved=True,
    )
    values.update(kwargs)
    return ProviderPortfolioPlan(**values)


def candidates():
    return [
        candidate("provider-a", ProviderRole.PRIMARY, group="vendor-a", priority=1),
        candidate("provider-b", ProviderRole.SECONDARY, group="vendor-b", priority=2),
        candidate("provider-c", ProviderRole.REFERENCE, group="vendor-c", priority=3),
    ]


def drill(**kwargs):
    values = dict(
        drill_id="drill-1",
        primary_provider_id="provider-a",
        fallback_provider_id="provider-b",
        started_at=NOW - timedelta(days=5, minutes=10),
        completed_at=NOW - timedelta(days=5),
        recovery_time_seconds=25,
        expected_recovery_time_seconds=60,
        data_loss_events=0,
        duplicate_events=0,
        reconciliation_passed=True,
        schema_compatible=True,
        identifiers_reconciled=True,
        rights_revalidated=True,
        human_observed=True,
    )
    values.update(kwargs)
    return FailoverDrillEvidence(**values)


def test_operational_profile_fingerprint_is_stable():
    assert op_profile().fingerprint == op_profile().fingerprint


@pytest.mark.parametrize("field,value", [
    ("availability_slo_bps", -1),
    ("min_coverage_bps", 10001),
    ("min_quality_score_bps", 10001),
    ("min_stable_id_rate_bps", -1),
    ("max_error_rate_bps", 10001),
    ("max_quota_utilization_bps", 10001),
])
def test_operational_profile_rejects_invalid_percentages(field, value):
    with pytest.raises(ValueError):
        op_profile(**{field: value})


def test_profile_rejects_p99_below_p95():
    with pytest.raises(ValueError):
        op_profile(max_p95_latency_ms=900, max_p99_latency_ms=500)


def test_profile_rejects_non_positive_budget():
    with pytest.raises(ValueError):
        op_profile(monthly_budget_cents=0)


def test_observation_rejects_nonaware_time():
    p = op_profile()
    with pytest.raises(ValueError):
        op_obs(p, observed_at=datetime(2026, 8, 18, 20, 0))


def test_observation_rejects_quota_remaining_above_limit():
    with pytest.raises(ValueError):
        op_obs(quota_limit_units=10, quota_remaining_units=11)


def test_observation_rejects_projected_cost_below_current():
    with pytest.raises(ValueError):
        op_obs(current_month_cost_cents=50000, projected_month_cost_cents=40000)


def test_healthy_provider_passes_operational_gate():
    p = op_profile()
    result = evaluate_provider_operational(p, op_obs(p), now=NOW)
    assert result.status is ProviderOperationalStatus.PASS
    assert result.automatic_provider_promotion is False
    assert result.automatic_wagering is False


def test_missing_observation_blocks():
    result = evaluate_provider_operational(op_profile(), None, now=NOW)
    assert result.status is ProviderOperationalStatus.BLOCK
    assert "MISSING_OPERATIONAL_OBSERVATION" in result.reasons


@pytest.mark.parametrize("kwargs,reason", [
    ({"availability_bps": 9800}, "AVAILABILITY_BELOW_SLO"),
    ({"p95_latency_ms": 501}, "P95_LATENCY_ABOVE_SLO"),
    ({"p99_latency_ms": 901}, "P99_LATENCY_ABOVE_SLO"),
    ({"p95_freshness_seconds": 61}, "DATA_FRESHNESS_ABOVE_SLO"),
    ({"coverage_bps": 9490}, "COVERAGE_BELOW_MINIMUM"),
    ({"quality_score_bps": 9490}, "QUALITY_BELOW_MINIMUM"),
    ({"stable_id_rate_bps": 9890}, "STABLE_ID_RATE_BELOW_MINIMUM"),
    ({"error_rate_bps": 110}, "ERROR_RATE_ABOVE_MAXIMUM"),
])
def test_operational_slo_breaches_block(kwargs, reason):
    p = op_profile()
    result = evaluate_provider_operational(p, op_obs(p, **kwargs), now=NOW)
    assert result.status is ProviderOperationalStatus.BLOCK
    assert reason in result.reasons


def test_stale_observation_blocks():
    p = op_profile(observation_max_age_minutes=30)
    obs = op_obs(p, observed_at=NOW - timedelta(minutes=31), window_end=NOW - timedelta(minutes=35))
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "STALE_OPERATIONAL_OBSERVATION" in result.reasons


def test_future_observation_blocks():
    p = op_profile()
    obs = op_obs(p, observed_at=NOW + timedelta(minutes=1), window_end=NOW - timedelta(minutes=1))
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "FUTURE_OPERATIONAL_OBSERVATION" in result.reasons


def test_provider_mismatch_blocks():
    p = op_profile()
    obs = op_obs(p, provider_id="other")
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "PROVIDER_OPERATIONAL_PROFILE_MISMATCH" in result.reasons


def test_profile_fingerprint_mismatch_blocks():
    p = op_profile()
    obs = op_obs(p, profile_fingerprint=SHA)
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "OPERATIONAL_PROFILE_FINGERPRINT_MISMATCH" in result.reasons


def test_quota_utilization_blocks():
    p = op_profile(max_quota_utilization_bps=9000)
    obs = op_obs(p, quota_limit_units=1000, quota_remaining_units=90, expected_units_next_window=10)
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "QUOTA_UTILIZATION_ABOVE_MAXIMUM" in result.reasons


def test_quota_reserve_blocks():
    p = op_profile(min_quota_reserve_units=100)
    obs = op_obs(p, quota_remaining_units=99, expected_units_next_window=10)
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "QUOTA_RESERVE_BELOW_MINIMUM" in result.reasons


def test_next_window_quota_blocks():
    p = op_profile(min_quota_reserve_units=10)
    obs = op_obs(p, quota_remaining_units=100, expected_units_next_window=101)
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "INSUFFICIENT_QUOTA_FOR_NEXT_WINDOW" in result.reasons


def test_projected_cost_policy_blocks():
    p = op_profile(monthly_budget_cents=100000, max_projected_budget_utilization_bps=9000)
    obs = op_obs(p, projected_month_cost_cents=90100)
    result = evaluate_provider_operational(p, obs, now=NOW)
    assert "PROJECTED_COST_ABOVE_BUDGET_POLICY" in result.reasons


def test_open_provider_incident_blocks():
    p = op_profile()
    result = evaluate_provider_operational(p, op_obs(p, provider_incident_open=True), now=NOW)
    assert "PROVIDER_INCIDENT_OPEN" in result.reasons


def test_degraded_provider_is_watch_not_pass():
    p = op_profile()
    result = evaluate_provider_operational(p, op_obs(p, provider_degraded=True), now=NOW)
    assert result.status is ProviderOperationalStatus.WATCH


def test_near_latency_slo_is_watch():
    p = op_profile(max_p95_latency_ms=500)
    result = evaluate_provider_operational(p, op_obs(p, p95_latency_ms=460), now=NOW)
    assert result.status is ProviderOperationalStatus.WATCH
    assert "P95_LATENCY_NEAR_SLO" in result.reasons


def test_portfolio_requires_fallback():
    with pytest.raises(ValueError):
        plan(fallback_provider_ids=())


def test_portfolio_rejects_same_provider_in_multiple_roles():
    with pytest.raises(ValueError):
        plan(reference_provider_ids=("provider-a",))


def test_candidate_priority_must_be_positive():
    with pytest.raises(ValueError):
        candidate("provider-a", ProviderRole.PRIMARY, priority=0)


def test_healthy_portfolio_passes():
    result = evaluate_provider_portfolio(plan(), candidates())
    assert result.status is PortfolioStatus.PASS
    assert result.failover_ready is True
    assert result.automatic_provider_switch is False


def test_missing_primary_candidate_blocks():
    result = evaluate_provider_portfolio(plan(), candidates()[1:])
    assert result.status is PortfolioStatus.BLOCK
    assert "MISSING_PROVIDER_CANDIDATE:provider-a" in result.reasons


def test_primary_rights_block_blocks_portfolio():
    cs = candidates()
    cs[0] = candidate("provider-a", ProviderRole.PRIMARY, rights_status=ProviderRightsStatus.BLOCK, group="vendor-a")
    result = evaluate_provider_portfolio(plan(), cs)
    assert "PRIMARY_PROVIDER_RIGHTS_BLOCK" in result.reasons


def test_primary_operational_block_blocks_portfolio():
    cs = candidates()
    cs[0] = candidate("provider-a", ProviderRole.PRIMARY, status=ProviderOperationalStatus.BLOCK, group="vendor-a")
    result = evaluate_provider_portfolio(plan(), cs)
    assert "PRIMARY_PROVIDER_OPERATIONAL_BLOCK" in result.reasons


def test_primary_watch_produces_watch_if_failover_healthy():
    cs = candidates()
    cs[0] = candidate("provider-a", ProviderRole.PRIMARY, status=ProviderOperationalStatus.WATCH, group="vendor-a")
    result = evaluate_provider_portfolio(plan(), cs)
    assert result.status is PortfolioStatus.WATCH


def test_no_healthy_failover_blocks():
    cs = candidates()
    cs[1] = candidate("provider-b", ProviderRole.SECONDARY, status=ProviderOperationalStatus.BLOCK, group="vendor-b", priority=2)
    result = evaluate_provider_portfolio(plan(), cs)
    assert result.status is PortfolioStatus.BLOCK
    assert "NO_HEALTHY_FAILOVER_PROVIDER" in result.reasons


def test_non_independent_failover_blocks():
    cs = candidates()
    cs[1] = candidate("provider-b", ProviderRole.SECONDARY, group="vendor-a", priority=2)
    result = evaluate_provider_portfolio(plan(), cs)
    assert "FAILOVER_NOT_INDEPENDENT_FROM_PRIMARY" in result.reasons


def test_unapproved_portfolio_blocks():
    result = evaluate_provider_portfolio(plan(human_approved=False), candidates())
    assert "PORTFOLIO_PLAN_NOT_HUMAN_APPROVED" in result.reasons


def test_duplicate_candidate_rejected():
    cs = candidates() + [candidate("provider-a", ProviderRole.SECONDARY, priority=4)]
    with pytest.raises(ValueError):
        evaluate_provider_portfolio(plan(), cs)


def test_duplicate_priorities_watch():
    cs = candidates()
    cs[1] = candidate("provider-b", ProviderRole.SECONDARY, group="vendor-b", priority=1)
    result = evaluate_provider_portfolio(plan(), cs)
    assert result.status is PortfolioStatus.WATCH
    assert "DUPLICATE_PROVIDER_PRIORITIES" in result.reasons


def test_reference_rights_block_blocks_portfolio():
    cs = candidates()
    cs[2] = candidate("provider-c", ProviderRole.REFERENCE, rights_status=ProviderRightsStatus.BLOCK, group="vendor-c", priority=3)
    result = evaluate_provider_portfolio(plan(), cs)
    assert "REFERENCE_PROVIDER_RIGHTS_BLOCK:provider-c" in result.reasons


def test_reference_operational_block_is_watch():
    cs = candidates()
    cs[2] = candidate("provider-c", ProviderRole.REFERENCE, status=ProviderOperationalStatus.BLOCK, group="vendor-c", priority=3)
    result = evaluate_provider_portfolio(plan(), cs)
    assert result.status is PortfolioStatus.WATCH


def test_choose_failover_respects_priority_and_independence():
    p = plan(fallback_provider_ids=("provider-b", "provider-d"), reference_provider_ids=())
    cs = [
        candidate("provider-a", ProviderRole.PRIMARY, group="vendor-a", priority=1),
        candidate("provider-b", ProviderRole.SECONDARY, group="vendor-b", priority=3),
        candidate("provider-d", ProviderRole.SECONDARY, group="vendor-d", priority=2),
    ]
    result = choose_failover_candidate(p, cs)
    assert result is not None
    assert result.provider_id == "provider-d"


def test_choose_failover_returns_none_when_only_same_independence_group():
    p = plan(reference_provider_ids=())
    cs = [
        candidate("provider-a", ProviderRole.PRIMARY, group="same"),
        candidate("provider-b", ProviderRole.SECONDARY, group="same", priority=2),
    ]
    assert choose_failover_candidate(p, cs) is None


def test_failover_drill_passes_when_evidence_is_good():
    result = evaluate_failover_drill(drill(), now=NOW)
    assert result.status is FailoverDrillStatus.PASS
    assert result.automatic_failover_enabled is False


def test_missing_failover_drill_blocks():
    result = evaluate_failover_drill(None, now=NOW)
    assert result.status is FailoverDrillStatus.BLOCK


@pytest.mark.parametrize("kwargs,reason", [
    ({"recovery_time_seconds": 61}, "FAILOVER_RECOVERY_TIME_EXCEEDED"),
    ({"data_loss_events": 1}, "FAILOVER_DATA_LOSS_DETECTED"),
    ({"reconciliation_passed": False}, "FAILOVER_RECONCILIATION_FAILED"),
    ({"schema_compatible": False}, "FAILOVER_SCHEMA_INCOMPATIBLE"),
    ({"identifiers_reconciled": False}, "FAILOVER_IDENTIFIERS_NOT_RECONCILED"),
    ({"rights_revalidated": False}, "FAILOVER_RIGHTS_NOT_REVALIDATED"),
])
def test_failover_hard_failures_block(kwargs, reason):
    result = evaluate_failover_drill(drill(**kwargs), now=NOW)
    assert result.status is FailoverDrillStatus.BLOCK
    assert reason in result.reasons


def test_duplicate_events_make_failover_watch():
    result = evaluate_failover_drill(drill(duplicate_events=1), now=NOW)
    assert result.status is FailoverDrillStatus.WATCH


def test_unobserved_drill_is_watch():
    result = evaluate_failover_drill(drill(human_observed=False), now=NOW)
    assert result.status is FailoverDrillStatus.WATCH


def test_stale_drill_blocks():
    ev = drill(
        started_at=NOW - timedelta(days=101, minutes=10),
        completed_at=NOW - timedelta(days=101),
    )
    result = evaluate_failover_drill(ev, now=NOW, max_age_days=90)
    assert "STALE_FAILOVER_DRILL_EVIDENCE" in result.reasons


def test_future_drill_blocks():
    ev = drill(started_at=NOW + timedelta(minutes=1), completed_at=NOW + timedelta(minutes=2))
    result = evaluate_failover_drill(ev, now=NOW)
    assert "FUTURE_FAILOVER_DRILL_EVIDENCE" in result.reasons


def test_top_level_gate_passes_only_when_portfolio_and_drill_pass():
    pa = evaluate_provider_portfolio(plan(), candidates())
    fa = evaluate_failover_drill(drill(), now=NOW)
    result = evaluate_provider_portfolio_gate(pa, fa)
    assert result.status is ProviderPortfolioGateStatus.PASS
    assert result.provider_portfolio_certified is False
    assert result.automatic_provider_switch is False
    assert result.automatic_wagering is False


def test_top_level_gate_blocks_on_portfolio_block():
    pa = ProviderPortfolioAssessment(PortfolioStatus.BLOCK, ("x",), SHA, "provider-a", False)
    fa = FailoverDrillAssessment(FailoverDrillStatus.PASS, (), SHA2)
    result = evaluate_provider_portfolio_gate(pa, fa)
    assert result.status is ProviderPortfolioGateStatus.BLOCK


def test_top_level_gate_blocks_on_failover_block():
    pa = ProviderPortfolioAssessment(PortfolioStatus.PASS, (), SHA, "provider-a", True)
    fa = FailoverDrillAssessment(FailoverDrillStatus.BLOCK, ("x",), SHA2)
    result = evaluate_provider_portfolio_gate(pa, fa)
    assert result.status is ProviderPortfolioGateStatus.BLOCK


def test_top_level_gate_watch_propagates():
    pa = ProviderPortfolioAssessment(PortfolioStatus.WATCH, ("x",), SHA, "provider-a", True)
    fa = FailoverDrillAssessment(FailoverDrillStatus.PASS, (), SHA2)
    result = evaluate_provider_portfolio_gate(pa, fa)
    assert result.status is ProviderPortfolioGateStatus.WATCH


def test_top_level_gate_rejects_self_certification():
    with pytest.raises(ValueError):
        ProviderPortfolioGateResult(
            ProviderPortfolioGateStatus.PASS,
            (),
            SHA,
            SHA2,
            provider_portfolio_certified=True,
        )
