from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.security.provider_normalization import (
    CanonicalFixtureIdentity,
    CrosswalkStatus,
    EntityCrosswalkEntry,
    EntityKind,
    audit_crosswalk_conflicts,
    resolve_entity,
)
from app.security.provider_reconciliation import (
    EventState,
    MarketIdentity,
    ProviderEventSnapshot,
    ReconciliationPolicy,
    ReconciliationStatus,
    StatisticValue,
    reconcile_snapshots,
)
from app.security.provider_failover_consistency import (
    FailoverConsistencyPolicy,
    FailoverConsistencySample,
    FailoverConsistencyStatus,
    evaluate_failover_consistency,
)

NOW = datetime(2026, 8, 19, 1, 30, tzinfo=timezone.utc)
SHA = "1" * 64


def crosswalk(**kwargs):
    values = dict(
        provider_id="provider-a",
        entity_kind=EntityKind.TEAM,
        provider_entity_id="team-123",
        canonical_entity_id="team:real-madrid",
        mapping_version="v1",
        valid_from=NOW - timedelta(days=100),
        valid_to=None,
        confidence_bps=10000,
        evidence_sha256=SHA,
        human_reviewed=True,
    )
    values.update(kwargs)
    return EntityCrosswalkEntry(**values)


def fixture(**kwargs):
    values = dict(
        sport="football",
        canonical_fixture_id="fixture:2026-08-19:a:b",
        competition_id="competition:elite",
        home_entity_id="team:a",
        away_entity_id="team:b",
        kickoff_utc=NOW + timedelta(hours=1),
        venue_entity_id="venue:1",
        round_key="round-5",
    )
    values.update(kwargs)
    return CanonicalFixtureIdentity(**values)


def market(line=2500, selection="OVER", market_type="TOTAL_GOALS", period="FULL_TIME"):
    return MarketIdentity(market_type=market_type, period=period, selection=selection, line_milli=line)


def snapshot(provider_id="provider-a", **kwargs):
    f = kwargs.pop("fixture", fixture())
    values = dict(
        snapshot_id=f"snap-{provider_id}",
        provider_id=provider_id,
        provider_fixture_id=f"external-{provider_id}",
        fixture=f,
        observed_at=NOW - timedelta(seconds=5),
        event_time=NOW - timedelta(seconds=6),
        state=EventState.LIVE,
        home_score=1,
        away_score=0,
        statistics=(
            StatisticValue("shots", 10, 7),
            StatisticValue("shots_on_target", 4, 3),
            StatisticValue("corners", 5, 2),
        ),
        available_markets=(
            market(2500, "OVER"),
            market(2500, "UNDER"),
            MarketIdentity("MATCH_WINNER", "FULL_TIME", "HOME", None),
        ),
    )
    values.update(kwargs)
    return ProviderEventSnapshot(**values)


def policy(**kwargs):
    values = dict(
        max_snapshot_age_seconds=60,
        max_observation_skew_seconds=10,
        max_kickoff_delta_seconds=30,
        required_stat_metrics=("shots", "shots_on_target", "corners"),
        max_stat_absolute_delta=1,
        required_market_keys=(market(2500, "OVER").key,),
        allow_state_lag_live_to_paused=True,
    )
    values.update(kwargs)
    return ReconciliationPolicy(**values)


def reconciliation(status=ReconciliationStatus.PASS):
    left = snapshot("provider-a")
    right = snapshot("provider-b")
    result = reconcile_snapshots(left, right, policy(), now=NOW)
    if status is result.status:
        return result
    # produce a real assessment in the desired state instead of constructing one by hand
    if status is ReconciliationStatus.WATCH:
        return reconcile_snapshots(
            left,
            snapshot("provider-b", fixture=fixture(kickoff_utc=fixture().kickoff_utc + timedelta(seconds=5))),
            policy(),
            now=NOW,
        )
    return reconcile_snapshots(left, snapshot("provider-b", home_score=2), policy(), now=NOW)


def sample(i=0, status=ReconciliationStatus.PASS, **kwargs):
    values = dict(
        sample_id=f"sample-{i}",
        primary_provider_id="provider-a",
        fallback_provider_id="provider-b",
        checked_at=NOW - timedelta(seconds=(2 - i) * 10),
        reconciliation=reconciliation(status),
    )
    values.update(kwargs)
    return FailoverConsistencySample(**values)


# ---------- normalization / crosswalk ----------

def test_crosswalk_fingerprint_is_deterministic():
    assert crosswalk().fingerprint == crosswalk().fingerprint


def test_crosswalk_requires_aware_valid_from():
    with pytest.raises(ValueError):
        crosswalk(valid_from=datetime(2026, 8, 1))


def test_crosswalk_rejects_invalid_sha():
    with pytest.raises(ValueError):
        crosswalk(evidence_sha256="abc")


def test_crosswalk_rejects_invalid_confidence_bps():
    with pytest.raises(ValueError):
        crosswalk(confidence_bps=10001)


def test_crosswalk_rejects_valid_to_before_valid_from():
    with pytest.raises(ValueError):
        crosswalk(valid_from=NOW, valid_to=NOW - timedelta(seconds=1))


def test_resolve_entity_passes_for_exact_active_mapping():
    result = resolve_entity(
        (crosswalk(),),
        provider_id="provider-a",
        entity_kind=EntityKind.TEAM,
        provider_entity_id="team-123",
        at=NOW,
    )
    assert result.status is CrosswalkStatus.PASS
    assert result.canonical_entity_id == "team:real-madrid"


def test_resolve_entity_missing_mapping_blocks():
    result = resolve_entity((), provider_id="x", entity_kind=EntityKind.TEAM, provider_entity_id="1", at=NOW)
    assert result.status is CrosswalkStatus.BLOCK
    assert "MISSING_ACTIVE_CROSSWALK" in result.reasons


def test_resolve_entity_conflicting_active_mapping_blocks():
    entries = (crosswalk(), crosswalk(canonical_entity_id="team:other", mapping_version="v2"))
    result = resolve_entity(entries, provider_id="provider-a", entity_kind=EntityKind.TEAM, provider_entity_id="team-123", at=NOW)
    assert result.status is CrosswalkStatus.BLOCK
    assert "CONFLICTING_ACTIVE_CROSSWALK" in result.reasons


def test_low_confidence_mapping_is_watch():
    result = resolve_entity((crosswalk(confidence_bps=9800),), provider_id="provider-a", entity_kind=EntityKind.TEAM, provider_entity_id="team-123", at=NOW)
    assert result.status is CrosswalkStatus.WATCH
    assert "CROSSWALK_CONFIDENCE_BELOW_MINIMUM" in result.reasons


def test_unreviewed_mapping_is_watch():
    result = resolve_entity((crosswalk(human_reviewed=False),), provider_id="provider-a", entity_kind=EntityKind.TEAM, provider_entity_id="team-123", at=NOW)
    assert result.status is CrosswalkStatus.WATCH
    assert "CROSSWALK_NOT_HUMAN_REVIEWED" in result.reasons


def test_historical_mapping_resolves_at_historical_time():
    old = crosswalk(valid_from=NOW - timedelta(days=100), valid_to=NOW - timedelta(days=10), canonical_entity_id="team:old")
    new = crosswalk(valid_from=NOW - timedelta(days=10), canonical_entity_id="team:new", mapping_version="v2")
    result = resolve_entity((old, new), provider_id="provider-a", entity_kind=EntityKind.TEAM, provider_entity_id="team-123", at=NOW - timedelta(days=20))
    assert result.canonical_entity_id == "team:old"


def test_temporal_conflict_audit_detects_overlapping_conflicts():
    issues = audit_crosswalk_conflicts((crosswalk(), crosswalk(canonical_entity_id="team:other", mapping_version="v2")))
    assert issues
    assert issues[0].startswith("CROSSWALK_TEMPORAL_CONFLICT")


def test_temporal_conflict_audit_allows_nonoverlapping_reassignment():
    old = crosswalk(valid_to=NOW - timedelta(days=10), canonical_entity_id="team:old")
    new = crosswalk(valid_from=NOW - timedelta(days=10), canonical_entity_id="team:new", mapping_version="v2")
    assert audit_crosswalk_conflicts((old, new)) == ()


def test_fixture_rejects_same_home_and_away():
    with pytest.raises(ValueError):
        fixture(home_entity_id="team:a", away_entity_id="team:a")


def test_fixture_fingerprint_is_deterministic():
    assert fixture().fingerprint == fixture().fingerprint


# ---------- market identity ----------

def test_market_identity_keeps_line_in_key():
    assert market(2500).key != market(3500).key


def test_market_identity_rejects_float_line():
    with pytest.raises(TypeError):
        MarketIdentity("TOTAL_GOALS", "FULL_TIME", "OVER", 2.5)  # type: ignore[arg-type]


def test_market_identity_distinguishes_period():
    assert market(period="FULL_TIME").key != market(period="FIRST_HALF").key


def test_market_identity_distinguishes_selection():
    assert market(selection="OVER").key != market(selection="UNDER").key


# ---------- snapshot validation ----------

def test_snapshot_fingerprint_is_deterministic():
    assert snapshot().fingerprint == snapshot().fingerprint


def test_snapshot_rejects_future_event_time_relative_to_observed_at():
    with pytest.raises(ValueError):
        snapshot(event_time=NOW, observed_at=NOW - timedelta(seconds=1))


def test_snapshot_rejects_duplicate_statistics():
    with pytest.raises(ValueError):
        snapshot(statistics=(StatisticValue("shots", 1, 2), StatisticValue("shots", 2, 3)))


def test_snapshot_rejects_duplicate_market_identity():
    m = market()
    with pytest.raises(ValueError):
        snapshot(available_markets=(m, m))


def test_statistic_values_are_exact_integers():
    with pytest.raises(TypeError):
        StatisticValue("xg_milli", 1200.0, 900)  # type: ignore[arg-type]


# ---------- reconciliation ----------

def test_identical_normalized_cross_provider_snapshots_pass():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b"), policy(), now=NOW)
    assert result.status is ReconciliationStatus.PASS
    assert result.automatic_provider_switch is False
    assert result.automatic_wagering is False


def test_same_provider_cannot_reconcile_as_failover_pair():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-a", snapshot_id="other"), policy(), now=NOW)
    assert result.status is ReconciliationStatus.BLOCK
    assert "PROVIDERS_MUST_DIFFER" in result.reasons


@pytest.mark.parametrize("fixture_kwargs,reason", [
    ({"canonical_fixture_id": "fixture:other"}, "CANONICAL_FIXTURE_MISMATCH"),
    ({"competition_id": "competition:other"}, "COMPETITION_MISMATCH"),
    ({"home_entity_id": "team:x"}, "HOME_ENTITY_MISMATCH"),
    ({"away_entity_id": "team:y"}, "AWAY_ENTITY_MISMATCH"),
])
def test_fixture_identity_mismatches_block(fixture_kwargs, reason):
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", fixture=fixture(**fixture_kwargs)), policy(), now=NOW)
    assert result.status is ReconciliationStatus.BLOCK
    assert reason in result.reasons


def test_kickoff_small_difference_is_watch():
    result = reconcile_snapshots(
        snapshot("provider-a"),
        snapshot("provider-b", fixture=fixture(kickoff_utc=fixture().kickoff_utc + timedelta(seconds=10))),
        policy(),
        now=NOW,
    )
    assert result.status is ReconciliationStatus.WATCH
    assert "KICKOFF_WITHIN_TOLERANCE" in result.reasons


def test_kickoff_large_difference_blocks():
    result = reconcile_snapshots(
        snapshot("provider-a"),
        snapshot("provider-b", fixture=fixture(kickoff_utc=fixture().kickoff_utc + timedelta(seconds=31))),
        policy(),
        now=NOW,
    )
    assert "KICKOFF_MISMATCH" in result.reasons


def test_stale_primary_snapshot_blocks():
    result = reconcile_snapshots(snapshot("provider-a", observed_at=NOW - timedelta(seconds=61), event_time=NOW - timedelta(seconds=62)), snapshot("provider-b"), policy(), now=NOW)
    assert "PRIMARY_SNAPSHOT_STALE" in result.reasons


def test_future_fallback_snapshot_blocks():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", observed_at=NOW + timedelta(seconds=1), event_time=NOW), policy(), now=NOW)
    assert "FALLBACK_SNAPSHOT_FROM_FUTURE" in result.reasons


def test_observation_skew_blocks():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", observed_at=NOW - timedelta(seconds=20), event_time=NOW - timedelta(seconds=21)), policy(), now=NOW)
    assert "OBSERVATION_SKEW_EXCEEDED" in result.reasons


def test_event_time_skew_blocks():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", event_time=NOW - timedelta(seconds=30)), policy(), now=NOW)
    assert "EVENT_TIME_SKEW_EXCEEDED" in result.reasons


def test_live_paused_lag_is_watch_when_policy_allows():
    result = reconcile_snapshots(snapshot("provider-a", state=EventState.LIVE), snapshot("provider-b", state=EventState.PAUSED), policy(), now=NOW)
    assert result.status is ReconciliationStatus.WATCH
    assert "STATE_LAG_WITHIN_ALLOWED_TRANSITION" in result.reasons


def test_live_scheduled_state_mismatch_blocks():
    result = reconcile_snapshots(snapshot("provider-a", state=EventState.LIVE), snapshot("provider-b", state=EventState.SCHEDULED), policy(), now=NOW)
    assert "EVENT_STATE_MISMATCH" in result.reasons


def test_terminal_state_mismatch_blocks():
    result = reconcile_snapshots(snapshot("provider-a", state=EventState.FINISHED), snapshot("provider-b", state=EventState.LIVE), policy(), now=NOW)
    assert "TERMINAL_EVENT_STATE_MISMATCH" in result.reasons


def test_score_mismatch_blocks():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", home_score=2), policy(), now=NOW)
    assert "SCORE_MISMATCH" in result.reasons


def test_missing_required_stat_blocks():
    stats = (StatisticValue("shots", 10, 7), StatisticValue("corners", 5, 2))
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", statistics=stats), policy(), now=NOW)
    assert "MISSING_REQUIRED_STAT:shots_on_target" in result.reasons


def test_stat_delta_within_tolerance_is_watch():
    stats = (
        StatisticValue("shots", 11, 7),
        StatisticValue("shots_on_target", 4, 3),
        StatisticValue("corners", 5, 2),
    )
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", statistics=stats), policy(), now=NOW)
    assert result.status is ReconciliationStatus.WATCH
    assert "STAT_DELTA_WITHIN_TOLERANCE:shots" in result.reasons


def test_stat_delta_above_tolerance_blocks():
    stats = (
        StatisticValue("shots", 12, 7),
        StatisticValue("shots_on_target", 4, 3),
        StatisticValue("corners", 5, 2),
    )
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", statistics=stats), policy(), now=NOW)
    assert "STAT_DELTA_EXCEEDED:shots" in result.reasons


def test_missing_required_market_on_fallback_blocks():
    only_winner = (MarketIdentity("MATCH_WINNER", "FULL_TIME", "HOME", None),)
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", available_markets=only_winner), policy(), now=NOW)
    assert any(reason.startswith("FALLBACK_MISSING_REQUIRED_MARKET") for reason in result.reasons)


def test_line_identity_prevents_over_25_from_matching_over_35():
    fallback_markets = (market(3500, "OVER"), market(2500, "UNDER"))
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b", available_markets=fallback_markets), policy(), now=NOW)
    assert any(reason.startswith("FALLBACK_MISSING_REQUIRED_MARKET") for reason in result.reasons)


def test_reconciliation_compared_market_keys_are_deterministic():
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b"), policy(), now=NOW)
    assert result.compared_market_keys == tuple(sorted(result.compared_market_keys))


def test_reconciliation_fingerprint_is_deterministic():
    a = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b"), policy(), now=NOW)
    b = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b"), policy(), now=NOW)
    assert a.fingerprint == b.fingerprint


def test_provider_price_equality_is_not_required_by_identity_reconciliation():
    # V21 intentionally models market identity, not equal prices. Different bookmaker/provider
    # odds can be legitimate and are handled by odds evidence/CLV components elsewhere.
    result = reconcile_snapshots(snapshot("provider-a"), snapshot("provider-b"), policy(), now=NOW)
    assert result.status is ReconciliationStatus.PASS


# ---------- failover consistency window ----------

def test_failover_consistency_requires_samples():
    result = evaluate_failover_consistency((), FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert result.status is FailoverConsistencyStatus.BLOCK


def test_three_consecutive_passes_are_required_and_pass():
    samples = (sample(0), sample(1), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert result.status is FailoverConsistencyStatus.PASS
    assert result.consistent_samples == 3
    assert result.automatic_provider_switch is False
    assert result.automatic_wagering is False
    assert result.production_certified is False


def test_insufficient_pass_samples_is_watch():
    result = evaluate_failover_consistency((sample(1), sample(2)), FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert result.status is FailoverConsistencyStatus.WATCH
    assert "INSUFFICIENT_CONSECUTIVE_RECONCILIATIONS" in result.reasons


def test_block_reconciliation_blocks_window():
    samples = (sample(0), sample(1, status=ReconciliationStatus.BLOCK), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert result.status is FailoverConsistencyStatus.BLOCK
    assert "RECONCILIATION_BLOCK_IN_WINDOW" in result.reasons


def test_watch_reconciliation_blocks_when_not_allowed():
    samples = (sample(0), sample(1, status=ReconciliationStatus.WATCH), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30, allow_watch_samples=False), now=NOW)
    assert "RECONCILIATION_WATCH_NOT_ALLOWED" in result.reasons


def test_watch_reconciliation_is_watch_when_allowed():
    samples = (sample(0), sample(1, status=ReconciliationStatus.WATCH), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(1, 10, 30, allow_watch_samples=True), now=NOW)
    assert result.status is FailoverConsistencyStatus.WATCH
    assert "RECONCILIATION_WATCH_IN_WINDOW" in result.reasons


def test_provider_pair_change_blocks_window():
    samples = (sample(0), sample(1, fallback_provider_id="provider-c"), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert "FAILOVER_PROVIDER_PAIR_CHANGED" in result.reasons


def test_duplicate_sample_id_blocks_window():
    samples = (sample(0), sample(1, sample_id="sample-0"), sample(2))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert "DUPLICATE_FAILOVER_SAMPLE_ID" in result.reasons


def test_future_sample_blocks_window():
    samples = (sample(0), sample(1), sample(2, checked_at=NOW + timedelta(seconds=1)))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert "FAILOVER_SAMPLE_FROM_FUTURE" in result.reasons


def test_stale_window_blocks():
    samples = tuple(sample(i, checked_at=NOW - timedelta(minutes=20, seconds=(2-i)*10)) for i in range(3))
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert "FAILOVER_CONSISTENCY_WINDOW_STALE" in result.reasons


def test_large_gap_blocks_window():
    samples = (
        sample(0, checked_at=NOW - timedelta(seconds=100)),
        sample(1, checked_at=NOW - timedelta(seconds=20)),
        sample(2, checked_at=NOW - timedelta(seconds=10)),
    )
    result = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert "FAILOVER_SAMPLE_GAP_EXCEEDED" in result.reasons


def test_failover_consistency_fingerprint_is_deterministic():
    samples = (sample(0), sample(1), sample(2))
    a = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    b = evaluate_failover_consistency(samples, FailoverConsistencyPolicy(3, 10, 30), now=NOW)
    assert a.fingerprint == b.fingerprint


def test_failover_sample_rejects_same_provider_pair():
    with pytest.raises(ValueError):
        sample(0, fallback_provider_id="provider-a")


def test_failover_policy_rejects_nonpositive_values():
    with pytest.raises(ValueError):
        FailoverConsistencyPolicy(0, 10, 30)
