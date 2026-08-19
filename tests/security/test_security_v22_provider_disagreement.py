from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.security.provider_disagreement import (
    DisagreementPolicy,
    DisagreementStatus,
    ProviderIndependence,
    build_quarantine_record,
    resolve_provider_disagreement,
)
from app.security.provider_normalization import CanonicalFixtureIdentity
from app.security.provider_quarantine import (
    ProviderQuarantineRecord,
    QuarantineReleaseEvidence,
    QuarantineReleaseStatus,
    QuarantineState,
    evaluate_quarantine_release,
)
from app.security.provider_reconciliation import (
    EventState,
    MarketIdentity,
    ProviderEventSnapshot,
    ReconciliationPolicy,
    StatisticValue,
)
from app.security.provider_source_of_truth import (
    AuthorityStatus,
    SourceOfTruthRule,
    TruthDomain,
    audit_source_of_truth_conflicts,
    resolve_source_of_truth,
)

NOW = datetime(2026, 8, 19, 1, 30, tzinfo=timezone.utc)
SHA = "a" * 64
RES_SHA = "b" * 64


def fixture(**kwargs):
    values = dict(
        sport="football",
        canonical_fixture_id="fixture:elite:a:b",
        competition_id="competition:elite",
        home_entity_id="team:a",
        away_entity_id="team:b",
        kickoff_utc=NOW + timedelta(hours=1),
        venue_entity_id="venue:1",
        round_key="round-5",
    )
    values.update(kwargs)
    return CanonicalFixtureIdentity(**values)


def market(line=2500, selection="OVER"):
    return MarketIdentity("TOTAL_GOALS", "FULL_TIME", selection, line)


def snapshot(provider_id="provider-a", **kwargs):
    values = dict(
        snapshot_id=f"snap-{provider_id}",
        provider_id=provider_id,
        provider_fixture_id=f"ext-{provider_id}",
        fixture=fixture(),
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
        available_markets=(market(), market(selection="UNDER")),
    )
    values.update(kwargs)
    return ProviderEventSnapshot(**values)


def reconciliation_policy(**kwargs):
    values = dict(
        max_snapshot_age_seconds=60,
        max_observation_skew_seconds=10,
        max_kickoff_delta_seconds=30,
        required_stat_metrics=("shots", "shots_on_target", "corners"),
        max_stat_absolute_delta=1,
        required_market_keys=(market().key,),
    )
    values.update(kwargs)
    return ReconciliationPolicy(**values)


def independence():
    return (
        ProviderIndependence("provider-a", "group-a"),
        ProviderIndependence("provider-b", "group-b"),
        ProviderIndependence("provider-c", "group-c"),
    )


def truth_rule(**kwargs):
    values = dict(
        rule_id="truth-1",
        provider_id="provider-a",
        sport="football",
        competition_id="competition:elite",
        domain=TruthDomain.STATISTICS,
        valid_from=NOW - timedelta(days=5),
        valid_to=None,
        evidence_sha256=SHA,
        confidence_bps=10000,
        human_approved=True,
        independent_reviewed=True,
        policy_version="v22",
    )
    values.update(kwargs)
    return SourceOfTruthRule(**values)


# ---- source-of-truth registry ----

def test_truth_rule_fingerprint_is_deterministic():
    assert truth_rule().fingerprint == truth_rule().fingerprint


def test_truth_rule_requires_aware_time():
    with pytest.raises(ValueError):
        truth_rule(valid_from=datetime(2026, 8, 1))


def test_truth_rule_rejects_invalid_sha():
    with pytest.raises(ValueError):
        truth_rule(evidence_sha256="abc")


def test_truth_rule_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        truth_rule(confidence_bps=10001)


def test_truth_rule_rejects_invalid_window():
    with pytest.raises(ValueError):
        truth_rule(valid_from=NOW, valid_to=NOW - timedelta(seconds=1))


def test_source_of_truth_passes_for_single_governed_rule():
    result = resolve_source_of_truth(
        (truth_rule(),),
        provider_ids=("provider-a", "provider-b"),
        sport="football",
        competition_id="competition:elite",
        domain=TruthDomain.STATISTICS,
        at=NOW,
    )
    assert result.status is AuthorityStatus.PASS
    assert result.provider_id == "provider-a"
    assert result.source_of_truth_certified is False


def test_source_of_truth_missing_rule_blocks():
    result = resolve_source_of_truth(
        (), provider_ids=("provider-a", "provider-b"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert result.status is AuthorityStatus.BLOCK
    assert "NO_ACTIVE_SOURCE_OF_TRUTH_RULE" in result.reasons


def test_source_of_truth_conflicting_active_providers_block():
    result = resolve_source_of_truth(
        (truth_rule(), truth_rule(rule_id="truth-2", provider_id="provider-b")),
        provider_ids=("provider-a", "provider-b"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert result.status is AuthorityStatus.BLOCK
    assert "CONFLICTING_SOURCE_OF_TRUTH_RULES" in result.reasons


def test_source_of_truth_low_confidence_is_watch():
    result = resolve_source_of_truth(
        (truth_rule(confidence_bps=9800),), provider_ids=("provider-a", "provider-b"),
        sport="football", competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert result.status is AuthorityStatus.WATCH


def test_source_of_truth_requires_human_approval():
    result = resolve_source_of_truth(
        (truth_rule(human_approved=False),), provider_ids=("provider-a", "provider-b"),
        sport="football", competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert "SOURCE_OF_TRUTH_NOT_HUMAN_APPROVED" in result.reasons


def test_source_of_truth_requires_independent_review():
    result = resolve_source_of_truth(
        (truth_rule(independent_reviewed=False),), provider_ids=("provider-a", "provider-b"),
        sport="football", competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert "SOURCE_OF_TRUTH_NOT_INDEPENDENTLY_REVIEWED" in result.reasons


def test_source_of_truth_duplicate_provider_set_blocks():
    result = resolve_source_of_truth(
        (truth_rule(),), provider_ids=("provider-a", "provider-a"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    assert result.status is AuthorityStatus.BLOCK


def test_source_of_truth_temporal_conflict_audit_detects_overlap():
    issues = audit_source_of_truth_conflicts((truth_rule(), truth_rule(rule_id="truth-2", provider_id="provider-b")))
    assert issues == ("SOURCE_OF_TRUTH_TEMPORAL_CONFLICT:football:competition:elite:STATISTICS",)


def test_source_of_truth_temporal_conflict_allows_nonoverlap():
    old = truth_rule(valid_from=NOW - timedelta(days=20), valid_to=NOW - timedelta(days=10))
    new = truth_rule(rule_id="truth-2", provider_id="provider-b", valid_from=NOW - timedelta(days=10))
    assert audit_source_of_truth_conflicts((old, new)) == ()


# ---- disagreement resolution ----

def test_clean_pair_passes_without_third_source():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b"), reconciliation_policy(), DisagreementPolicy(), now=NOW
    )
    assert result.status is DisagreementStatus.PASS
    assert result.quarantine_required is False
    assert result.automatic_provider_switch is False
    assert result.automatic_wagering is False


def test_tolerable_pair_difference_is_watch_not_quarantine():
    other_stats = (
        StatisticValue("shots", 11, 7),
        StatisticValue("shots_on_target", 4, 3),
        StatisticValue("corners", 5, 2),
    )
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", statistics=other_stats),
        reconciliation_policy(), DisagreementPolicy(), now=NOW
    )
    assert result.status is DisagreementStatus.WATCH
    assert result.quarantine_required is False


def test_score_disagreement_without_third_source_quarantines():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "THIRD_SOURCE_REQUIRED" in result.reasons


def test_event_state_disagreement_without_third_source_quarantines():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", state=EventState.FINISHED),
        reconciliation_policy(), DisagreementPolicy(), now=NOW
    )
    assert result.status is DisagreementStatus.QUARANTINE


def test_identity_disagreement_never_uses_third_source_to_auto_resolve():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", fixture=fixture(canonical_fixture_id="fixture:other")),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c"), independence=independence(),
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "NON_TIEBREAKABLE_DISAGREEMENT" in result.reasons


def test_market_identity_gap_is_non_tiebreakable():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", available_markets=()),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c"), independence=independence(),
    )
    assert result.status is DisagreementStatus.QUARANTINE


def test_independent_third_source_supporting_primary_resolves_to_watch():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c"), independence=independence(),
    )
    assert result.status is DisagreementStatus.WATCH
    assert result.selected_evidence_fingerprint == snapshot("provider-a").fingerprint
    assert "THIRD_SOURCE_SUPPORTS_PRIMARY" in result.reasons


def test_independent_third_source_supporting_fallback_resolves_to_watch():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c", home_score=2), independence=independence(),
    )
    assert result.status is DisagreementStatus.WATCH
    assert result.selected_evidence_fingerprint == snapshot("provider-b", home_score=2).fingerprint
    assert "THIRD_SOURCE_SUPPORTS_FALLBACK" in result.reasons


def test_third_source_must_be_distinct():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-a", snapshot_id="third"), independence=independence(),
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "THIRD_SOURCE_NOT_DISTINCT" in result.reasons


def test_third_source_requires_independence_evidence():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c"), independence=(),
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert any(reason.startswith("MISSING_INDEPENDENCE_EVIDENCE") for reason in result.reasons)


def test_third_source_same_independence_group_is_quarantined():
    groups = (
        ProviderIndependence("provider-a", "group-a"),
        ProviderIndependence("provider-b", "group-b"),
        ProviderIndependence("provider-c", "group-a"),
    )
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c"), independence=groups,
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "THIRD_SOURCE_NOT_INDEPENDENT" in result.reasons


def test_duplicate_independence_evidence_raises():
    groups = independence() + (ProviderIndependence("provider-c", "group-x"),)
    with pytest.raises(ValueError):
        resolve_provider_disagreement(
            snapshot("provider-a"), snapshot("provider-b", home_score=2),
            reconciliation_policy(), DisagreementPolicy(), now=NOW,
            third=snapshot("provider-c"), independence=groups,
        )


def test_third_source_that_matches_neither_side_quarantines():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
        third=snapshot("provider-c", home_score=3), independence=independence(),
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "THIRD_SOURCE_DID_NOT_RESOLVE_DISAGREEMENT" in result.reasons


def test_statistics_disagreement_may_use_governed_authority():
    changed = (
        StatisticValue("shots", 20, 7),
        StatisticValue("shots_on_target", 4, 3),
        StatisticValue("corners", 5, 2),
    )
    authority = resolve_source_of_truth(
        (truth_rule(),), provider_ids=("provider-a", "provider-b"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", statistics=changed),
        reconciliation_policy(), DisagreementPolicy(), now=NOW, authority=authority,
    )
    assert result.status is DisagreementStatus.WATCH
    assert result.resolved_by == "GOVERNED_SOURCE_OF_TRUTH"
    assert result.selected_evidence_fingerprint == snapshot("provider-a").fingerprint


def test_statistics_authority_can_be_disabled_by_policy():
    changed = (
        StatisticValue("shots", 20, 7),
        StatisticValue("shots_on_target", 4, 3),
        StatisticValue("corners", 5, 2),
    )
    authority = resolve_source_of_truth(
        (truth_rule(),), provider_ids=("provider-a", "provider-b"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.STATISTICS, at=NOW,
    )
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", statistics=changed), reconciliation_policy(),
        DisagreementPolicy(allow_authority_for_statistics=False), now=NOW, authority=authority,
    )
    assert result.status is DisagreementStatus.QUARANTINE


def test_score_disagreement_cannot_be_overridden_by_authority_rule():
    score_rule = truth_rule(domain=TruthDomain.SCORE)
    authority = resolve_source_of_truth(
        (score_rule,), provider_ids=("provider-a", "provider-b"), sport="football",
        competition_id="competition:elite", domain=TruthDomain.SCORE, at=NOW,
    )
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2), reconciliation_policy(),
        DisagreementPolicy(), now=NOW, authority=authority,
    )
    assert result.status is DisagreementStatus.QUARANTINE
    assert "THIRD_SOURCE_REQUIRED" in result.reasons


def test_stale_snapshot_without_authority_quarantines():
    result = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", observed_at=NOW - timedelta(minutes=10), event_time=NOW - timedelta(minutes=10, seconds=1)),
        reconciliation_policy(), DisagreementPolicy(), now=NOW,
    )
    assert result.status is DisagreementStatus.QUARANTINE


def test_disagreement_resolution_fingerprint_is_deterministic():
    one = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2), reconciliation_policy(),
        DisagreementPolicy(), now=NOW,
    )
    two = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2), reconciliation_policy(),
        DisagreementPolicy(), now=NOW,
    )
    assert one.fingerprint == two.fingerprint


def test_disagreement_policy_rejects_zero_ttl():
    with pytest.raises(ValueError):
        DisagreementPolicy(quarantine_ttl_seconds=0)


# ---- quarantine ----

def quarantined_resolution():
    return resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b", home_score=2), reconciliation_policy(),
        DisagreementPolicy(), now=NOW,
    )


def quarantine_record(**kwargs):
    values = dict(
        quarantine_id="q-1",
        canonical_fixture_id="fixture:elite:a:b",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        reason_codes=("SCORE_MISMATCH", "THIRD_SOURCE_REQUIRED"),
        source_snapshot_fingerprints=(snapshot("provider-a").fingerprint, snapshot("provider-b", home_score=2).fingerprint),
        state=QuarantineState.OPEN,
    )
    values.update(kwargs)
    return ProviderQuarantineRecord(**values)


def release_evidence(record=None, **kwargs):
    record = record or quarantine_record()
    values = dict(
        quarantine_fingerprint=record.fingerprint,
        resolution_fingerprint=RES_SHA,
        reviewed_at=NOW + timedelta(seconds=10),
        reviewer_id="reviewer-2",
        independent_reviewer=True,
        human_approved=True,
        required_checks_passed=True,
    )
    values.update(kwargs)
    return QuarantineReleaseEvidence(**values)


def test_quarantine_record_can_be_built_from_resolution():
    result = quarantined_resolution()
    record = build_quarantine_record(
        result, quarantine_id="q-built", canonical_fixture_id="fixture:elite:a:b",
        now=NOW, policy=DisagreementPolicy(),
    )
    assert record.state is QuarantineState.OPEN
    assert record.automatic_release is False
    assert record.expires_at == NOW + timedelta(seconds=300)


def test_non_quarantine_resolution_cannot_create_record():
    clean = resolve_provider_disagreement(
        snapshot("provider-a"), snapshot("provider-b"), reconciliation_policy(), DisagreementPolicy(), now=NOW
    )
    with pytest.raises(ValueError):
        build_quarantine_record(clean, quarantine_id="q", canonical_fixture_id="fixture:elite:a:b", now=NOW, policy=DisagreementPolicy())


def test_quarantine_requires_two_source_fingerprints():
    with pytest.raises(ValueError):
        quarantine_record(source_snapshot_fingerprints=(SHA,))


def test_quarantine_rejects_duplicate_fingerprints():
    with pytest.raises(ValueError):
        quarantine_record(source_snapshot_fingerprints=(SHA, SHA))


def test_quarantine_rejects_invalid_window():
    with pytest.raises(ValueError):
        quarantine_record(expires_at=NOW)


def test_quarantine_never_allows_automatic_release():
    with pytest.raises(ValueError):
        quarantine_record(automatic_release=True)


def test_release_missing_evidence_blocks():
    result = evaluate_quarantine_release(quarantine_record(), None, now=NOW + timedelta(seconds=20))
    assert result.status is QuarantineReleaseStatus.BLOCK
    assert "MISSING_RELEASE_EVIDENCE" in result.reasons


def test_release_passes_with_exact_independent_human_evidence():
    record = quarantine_record()
    evidence = release_evidence(record)
    result = evaluate_quarantine_release(record, evidence, now=NOW + timedelta(seconds=20))
    assert result.status is QuarantineReleaseStatus.PASS
    assert result.automatic_release is False
    assert result.automatic_provider_switch is False
    assert result.automatic_wagering is False


def test_release_fingerprint_mismatch_blocks():
    record = quarantine_record()
    evidence = release_evidence(record, quarantine_fingerprint=SHA)
    result = evaluate_quarantine_release(record, evidence, now=NOW + timedelta(seconds=20))
    assert "QUARANTINE_FINGERPRINT_MISMATCH" in result.reasons


def test_release_requires_human_approval():
    record = quarantine_record()
    result = evaluate_quarantine_release(record, release_evidence(record, human_approved=False), now=NOW + timedelta(seconds=20))
    assert "RELEASE_NOT_HUMAN_APPROVED" in result.reasons


def test_release_requires_independent_reviewer():
    record = quarantine_record()
    result = evaluate_quarantine_release(record, release_evidence(record, independent_reviewer=False), now=NOW + timedelta(seconds=20))
    assert "RELEASE_NOT_INDEPENDENTLY_REVIEWED" in result.reasons


def test_release_requires_checks_passed():
    record = quarantine_record()
    result = evaluate_quarantine_release(record, release_evidence(record, required_checks_passed=False), now=NOW + timedelta(seconds=20))
    assert "RELEASE_CHECKS_NOT_PASSED" in result.reasons


def test_release_from_future_blocks():
    record = quarantine_record()
    result = evaluate_quarantine_release(record, release_evidence(record, reviewed_at=NOW + timedelta(minutes=2)), now=NOW + timedelta(seconds=20))
    assert "REVIEW_FROM_FUTURE" in result.reasons


def test_release_predating_quarantine_blocks():
    record = quarantine_record()
    result = evaluate_quarantine_release(record, release_evidence(record, reviewed_at=NOW - timedelta(seconds=1)), now=NOW + timedelta(seconds=20))
    assert "REVIEW_PREDATES_QUARANTINE" in result.reasons


def test_expired_quarantine_requires_new_review_and_does_not_auto_release():
    record = quarantine_record(expires_at=NOW + timedelta(seconds=5))
    result = evaluate_quarantine_release(record, release_evidence(record), now=NOW + timedelta(seconds=20))
    assert result.status is QuarantineReleaseStatus.BLOCK
    assert "QUARANTINE_EXPIRED_REQUIRES_NEW_REVIEW" in result.reasons


def test_already_released_record_cannot_be_released_again():
    record = quarantine_record(state=QuarantineState.RELEASED)
    result = evaluate_quarantine_release(record, release_evidence(record), now=NOW + timedelta(seconds=20))
    assert "QUARANTINE_NOT_OPEN" in result.reasons


def test_quarantine_fingerprint_is_deterministic():
    assert quarantine_record().fingerprint == quarantine_record().fingerprint


def test_release_evidence_rejects_bad_resolution_sha():
    with pytest.raises(ValueError):
        release_evidence(resolution_fingerprint="bad")
