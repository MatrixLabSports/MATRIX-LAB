from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.security.provider_correction_gate import evaluate_provider_correction_gate
from app.security.provider_normalization import CanonicalFixtureIdentity
from app.security.provider_reconciliation import (
    EventState,
    MarketIdentity,
    ProviderEventSnapshot,
    StatisticValue,
)
from app.security.provider_revision_ledger import (
    GENESIS,
    ProviderRevisionLedger,
    verify_provider_revision_ledger,
)
from app.security.provider_temporal_training import build_training_truth_cutoff
from app.security.provider_temporal_truth import (
    DecisionEvidenceFreeze,
    RevisionImpactLevel,
    SnapshotDelta,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    TruthRevisionKind,
    ProviderTruthVersion,
    assess_post_decision_revision_impact,
    assess_truth_chain,
    diff_provider_snapshots,
    resolve_point_in_time_truth,
    validate_decision_evidence_freeze,
)

NOW = datetime(2026, 8, 19, 2, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def fixture(**kwargs):
    values = dict(
        sport="football",
        canonical_fixture_id="fixture:elite:a:b",
        competition_id="competition:elite",
        home_entity_id="team:a",
        away_entity_id="team:b",
        kickoff_utc=NOW - timedelta(hours=1),
        venue_entity_id="venue:1",
        round_key="round-1",
    )
    values.update(kwargs)
    return CanonicalFixtureIdentity(**values)


def market(line=2500, selection="OVER"):
    return MarketIdentity("TOTAL_GOALS", "FULL_TIME", selection, line)


def snapshot(
    *,
    snapshot_id="snap-initial",
    observed_at=None,
    event_time=None,
    home_score=0,
    away_score=0,
    state=EventState.LIVE,
    statistics=None,
    available_markets=None,
    fixture_value=None,
    provider_id="provider-a",
    provider_fixture_id="external-a",
):
    observed_at = observed_at or NOW - timedelta(minutes=30)
    event_time = event_time or observed_at
    return ProviderEventSnapshot(
        snapshot_id=snapshot_id,
        provider_id=provider_id,
        provider_fixture_id=provider_fixture_id,
        fixture=fixture_value or fixture(),
        observed_at=observed_at,
        event_time=event_time,
        state=state,
        home_score=home_score,
        away_score=away_score,
        statistics=statistics if statistics is not None else (
            StatisticValue("shots", 4, 2),
            StatisticValue("corners", 2, 1),
        ),
        available_markets=available_markets if available_markets is not None else (
            market(2500, "OVER"),
            market(2500, "UNDER"),
        ),
    )


def version(
    version_id="v1",
    *,
    snap=None,
    known_at=None,
    valid_from=None,
    kind=TruthRevisionKind.INITIAL,
    supersedes=None,
    correction_scope=(),
    reason_code=None,
    human_reviewed=False,
    evidence_sha256=SHA,
):
    snap = snap or snapshot()
    known_at = known_at or snap.observed_at
    valid_from = valid_from or snap.event_time
    return ProviderTruthVersion(
        version_id=version_id,
        provider_id=snap.provider_id,
        canonical_fixture_id=snap.fixture.canonical_fixture_id,
        provider_fixture_id=snap.provider_fixture_id,
        snapshot=snap,
        known_at=known_at,
        valid_from_event_time=valid_from,
        revision_kind=kind,
        supersedes_version_id=supersedes,
        correction_scope=tuple(correction_scope),
        reason_code=reason_code,
        evidence_sha256=evidence_sha256,
        human_reviewed=human_reviewed,
    )


def chain():
    s1 = snapshot(snapshot_id="snap-1", observed_at=NOW - timedelta(minutes=30), event_time=NOW - timedelta(minutes=30))
    v1 = version("v1", snap=s1)
    s2 = snapshot(
        snapshot_id="snap-2",
        observed_at=NOW - timedelta(minutes=20),
        event_time=NOW - timedelta(minutes=20),
        home_score=1,
        statistics=(StatisticValue("shots", 8, 4), StatisticValue("corners", 3, 1)),
    )
    v2 = version(
        "v2", snap=s2, known_at=s2.observed_at, valid_from=s2.event_time,
        kind=TruthRevisionKind.PROGRESSION, supersedes="v1",
    )
    s3 = snapshot(
        snapshot_id="snap-3-corrected",
        observed_at=NOW - timedelta(minutes=10),
        event_time=NOW - timedelta(minutes=20),
        home_score=0,
        statistics=(StatisticValue("shots", 8, 4), StatisticValue("corners", 3, 1)),
    )
    v3 = version(
        "v3", snap=s3, known_at=s3.observed_at, valid_from=NOW - timedelta(minutes=20),
        kind=TruthRevisionKind.CORRECTION, supersedes="v2",
        correction_scope=("HOME_SCORE",), reason_code="PROVIDER_SCORE_CORRECTION", human_reviewed=True,
    )
    return v1, v2, v3


def policy(**kwargs):
    values = dict(max_recording_delay_seconds=30, correction_review_age_seconds=3600)
    values.update(kwargs)
    return TemporalTruthPolicy(**values)


def freeze_for_v2(v2=None, decision_at=None, **kwargs):
    v2 = v2 or chain()[1]
    decision_at = decision_at or NOW - timedelta(minutes=15)
    values = dict(
        decision_id="decision-1",
        provider_id=v2.provider_id,
        canonical_fixture_id=v2.canonical_fixture_id,
        decision_at=decision_at,
        truth_version_id=v2.version_id,
        truth_version_fingerprint=v2.fingerprint,
        snapshot_fingerprint=v2.snapshot.fingerprint,
        model_version="model-1",
        market_key=market().key,
        evidence_sha256="b" * 64,
    )
    values.update(kwargs)
    return DecisionEvidenceFreeze(**values)


# ----- construction / canonical invariants -----

def test_truth_version_fingerprint_is_deterministic():
    assert version().fingerprint == version().fingerprint


def test_truth_version_requires_aware_known_at():
    with pytest.raises(ValueError):
        version(known_at=datetime(2026, 8, 19, 1, 0))


def test_truth_version_rejects_bad_evidence_sha():
    with pytest.raises(ValueError):
        version(evidence_sha256="abc")


def test_known_at_may_not_precede_observation():
    s = snapshot(observed_at=NOW - timedelta(minutes=20))
    with pytest.raises(ValueError):
        version(snap=s, known_at=NOW - timedelta(minutes=21))


def test_valid_from_may_not_be_after_known_at():
    with pytest.raises(ValueError):
        version(valid_from=NOW)


def test_initial_may_not_supersede():
    with pytest.raises(ValueError):
        version(supersedes="v0")


def test_progression_requires_supersedes():
    with pytest.raises(ValueError):
        version(kind=TruthRevisionKind.PROGRESSION)


def test_correction_requires_reason():
    with pytest.raises(ValueError):
        version(kind=TruthRevisionKind.CORRECTION, supersedes="v0", correction_scope=("HOME_SCORE",))


def test_correction_requires_scope():
    with pytest.raises(ValueError):
        version(kind=TruthRevisionKind.CORRECTION, supersedes="v0", reason_code="X")


def test_progression_may_not_declare_correction_scope():
    with pytest.raises(ValueError):
        version(kind=TruthRevisionKind.PROGRESSION, supersedes="v0", correction_scope=("HOME_SCORE",))


def test_duplicate_correction_scope_rejected():
    with pytest.raises(ValueError):
        version(
            kind=TruthRevisionKind.CORRECTION, supersedes="v0", reason_code="X",
            correction_scope=("HOME_SCORE", "HOME_SCORE"),
        )


def test_snapshot_provider_must_match_version():
    s = snapshot(provider_id="provider-b", provider_fixture_id="external-b")
    with pytest.raises(ValueError):
        ProviderTruthVersion(
            version_id="v1", provider_id="provider-a", canonical_fixture_id=s.fixture.canonical_fixture_id,
            provider_fixture_id=s.provider_fixture_id, snapshot=s, known_at=s.observed_at,
            valid_from_event_time=s.event_time, revision_kind=TruthRevisionKind.INITIAL,
            supersedes_version_id=None, correction_scope=(), reason_code=None, evidence_sha256=SHA,
        )


def test_automatic_model_promotion_is_forbidden():
    base = version()
    with pytest.raises(ValueError):
        replace(base, automatic_model_promotion=True)


def test_automatic_wagering_is_forbidden():
    base = version()
    with pytest.raises(ValueError):
        replace(base, automatic_wagering=True)


# ----- snapshot diff -----

def test_snapshot_diff_detects_score():
    left = snapshot()
    right = snapshot(snapshot_id="s2", home_score=1)
    delta = diff_provider_snapshots(left, right)
    assert "HOME_SCORE" in delta.fields
    assert "HOME_SCORE" in delta.critical_fields


def test_snapshot_diff_detects_state():
    delta = diff_provider_snapshots(snapshot(), snapshot(snapshot_id="s2", state=EventState.PAUSED))
    assert "EVENT_STATE" in delta.critical_fields


def test_snapshot_diff_detects_kickoff_without_identity_rewrite():
    delta = diff_provider_snapshots(
        snapshot(),
        snapshot(snapshot_id="s2", fixture_value=fixture(kickoff_utc=fixture().kickoff_utc + timedelta(minutes=5))),
    )
    assert "KICKOFF_UTC" in delta.fields
    assert delta.identity_changed is False


def test_snapshot_diff_detects_identity_rewrite():
    delta = diff_provider_snapshots(
        snapshot(), snapshot(snapshot_id="s2", fixture_value=fixture(home_entity_id="team:x"))
    )
    assert delta.identity_changed is True
    assert "HOME_ENTITY" in delta.critical_fields


def test_snapshot_diff_detects_stat_change():
    delta = diff_provider_snapshots(
        snapshot(),
        snapshot(snapshot_id="s2", statistics=(StatisticValue("shots", 5, 2), StatisticValue("corners", 2, 1))),
    )
    assert "STAT:shots" in delta.fields


def test_snapshot_diff_detects_stat_removal():
    delta = diff_provider_snapshots(
        snapshot(), snapshot(snapshot_id="s2", statistics=(StatisticValue("shots", 4, 2),))
    )
    assert "STAT:corners" in delta.fields


def test_snapshot_diff_detects_market_add_remove():
    left = snapshot()
    right = snapshot(snapshot_id="s2", available_markets=(market(3500, "OVER"),))
    fields = diff_provider_snapshots(left, right).fields
    assert any(item.startswith("MARKET_REMOVED:") for item in fields)
    assert any(item.startswith("MARKET_ADDED:") for item in fields)


def test_snapshot_diff_detects_event_time_revision():
    left = snapshot()
    right = snapshot(snapshot_id="s2", observed_at=left.observed_at + timedelta(minutes=1), event_time=left.event_time + timedelta(seconds=30))
    assert "EVENT_TIME" in diff_provider_snapshots(left, right).fields


def test_snapshot_diff_empty_for_equivalent_content_except_snapshot_id_and_observed_at():
    left = snapshot()
    right = snapshot(snapshot_id="s2", observed_at=left.observed_at + timedelta(seconds=1), event_time=left.event_time)
    # snapshot transport identity/observation time is not treated as provider fact correction.
    assert diff_provider_snapshots(left, right).fields == ()


# ----- chain assessment -----

def test_valid_chain_passes():
    result = assess_truth_chain(chain(), policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.PASS
    assert result.head_version_id == "v3"


def test_empty_chain_blocks():
    assert assess_truth_chain((), policy=policy(), now=NOW).status is TemporalTruthStatus.BLOCK


def test_chain_must_start_initial():
    v1, v2, _ = chain()
    result = assess_truth_chain((replace(v1, revision_kind=TruthRevisionKind.PROGRESSION, supersedes_version_id="v0"), v2), policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.BLOCK


def test_chain_rejects_duplicate_version_id():
    v1, v2, _ = chain()
    result = assess_truth_chain((v1, replace(v2, version_id="v1")), policy=policy(), now=NOW)
    assert "DUPLICATE_VERSION_ID" in result.reasons


def test_chain_rejects_provider_mismatch():
    v1, v2, _ = chain()
    s = snapshot(provider_id="provider-b", provider_fixture_id="external-b", snapshot_id="b", observed_at=NOW - timedelta(minutes=10), event_time=NOW - timedelta(minutes=10))
    vb = version("vb", snap=s)
    result = assess_truth_chain((v1, v2, vb), policy=policy(), now=NOW)
    assert "CHAIN_PROVIDER_MISMATCH" in result.reasons


def test_chain_rejects_fixture_mismatch():
    v1, _, _ = chain()
    s = snapshot(snapshot_id="other", fixture_value=fixture(canonical_fixture_id="fixture:other"))
    other = version("other", snap=s)
    result = assess_truth_chain((v1, other), policy=policy(), now=NOW)
    assert "CHAIN_CANONICAL_FIXTURE_MISMATCH" in result.reasons


def test_chain_rejects_non_linear_supersession():
    v1, v2, v3 = chain()
    result = assess_truth_chain((v1, v2, replace(v3, supersedes_version_id="v1")), policy=policy(), now=NOW)
    assert any(reason.startswith("NON_LINEAR_SUPERSESSION") for reason in result.reasons)


def test_chain_rejects_future_version():
    v1, v2, v3 = chain()
    future_snapshot = snapshot(snapshot_id="future", observed_at=NOW + timedelta(minutes=1), event_time=NOW)
    future = version("v4", snap=future_snapshot, known_at=NOW + timedelta(minutes=1), valid_from=NOW, kind=TruthRevisionKind.PROGRESSION, supersedes="v3")
    result = assess_truth_chain((v1, v2, v3, future), policy=policy(), now=NOW)
    assert any(reason.startswith("VERSION_FROM_FUTURE") for reason in result.reasons)


def test_chain_recording_delay_is_watch():
    v1 = version(known_at=snapshot().observed_at + timedelta(seconds=31))
    result = assess_truth_chain((v1,), policy=policy(max_recording_delay_seconds=30), now=NOW)
    assert result.status is TemporalTruthStatus.WATCH
    assert any(reason.startswith("RECORDING_DELAY_EXCEEDED") for reason in result.reasons)


def test_progression_cannot_move_validity_backwards():
    v1, v2, _ = chain()
    bad = replace(v2, valid_from_event_time=v1.valid_from_event_time - timedelta(seconds=1))
    result = assess_truth_chain((v1, bad), policy=policy(), now=NOW)
    assert any(reason.startswith("PROGRESSION_RETROACTIVE_VALIDITY") for reason in result.reasons)


def test_progression_event_time_cannot_regress():
    v1, v2, _ = chain()
    bad_snap = replace(v2.snapshot, event_time=v1.snapshot.event_time - timedelta(seconds=1))
    bad = replace(v2, snapshot=bad_snap, valid_from_event_time=v1.valid_from_event_time)
    result = assess_truth_chain((v1, bad), policy=policy(), now=NOW)
    assert any(reason.startswith("PROGRESSION_EVENT_TIME_REGRESSION") for reason in result.reasons)


def test_identity_rewrite_is_blocked_even_if_same_canonical_fixture_id():
    v1, v2, _ = chain()
    altered_fixture = replace(v2.snapshot.fixture, home_entity_id="team:x")
    bad_snap = replace(v2.snapshot, fixture=altered_fixture)
    bad = replace(v2, snapshot=bad_snap)
    result = assess_truth_chain((v1, bad), policy=policy(), now=NOW)
    assert any(reason.startswith("IDENTITY_REWRITE_BLOCKED") for reason in result.reasons)


def test_critical_score_correction_requires_human_review():
    v1, v2, v3 = chain()
    result = assess_truth_chain((v1, v2, replace(v3, human_reviewed=False)), policy=policy(), now=NOW)
    assert any(reason.startswith("CRITICAL_CORRECTION_NOT_HUMAN_REVIEWED") for reason in result.reasons)


def test_noncritical_stat_correction_can_pass_without_human_review():
    v1, v2, _ = chain()
    s3 = replace(
        v2.snapshot,
        snapshot_id="stat-fix",
        observed_at=NOW - timedelta(minutes=10),
        statistics=(StatisticValue("shots", 7, 4), StatisticValue("corners", 3, 1)),
    )
    v3 = version(
        "v3", snap=s3, known_at=s3.observed_at, valid_from=v2.valid_from_event_time,
        kind=TruthRevisionKind.CORRECTION, supersedes="v2", correction_scope=("STAT:shots",),
        reason_code="STAT_CORRECTION", human_reviewed=False,
    )
    assert assess_truth_chain((v1, v2, v3), policy=policy(), now=NOW).status is TemporalTruthStatus.PASS


def test_undeclared_correction_scope_blocks():
    v1, v2, v3 = chain()
    bad = replace(v3, correction_scope=("STAT:shots",))
    result = assess_truth_chain((v1, v2, bad), policy=policy(), now=NOW)
    assert any(reason.startswith("UNDECLARED_CORRECTION_SCOPE") for reason in result.reasons)


def test_declared_scope_without_delta_is_watch():
    v1, v2, v3 = chain()
    extra = replace(v3, correction_scope=("HOME_SCORE", "STAT:shots"))
    result = assess_truth_chain((v1, v2, extra), policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.WATCH
    assert any(reason.startswith("DECLARED_SCOPE_WITHOUT_DELTA") for reason in result.reasons)


def test_old_retroactive_correction_is_watch():
    v1, v2, v3 = chain()
    result = assess_truth_chain((v1, v2, v3), policy=policy(correction_review_age_seconds=60), now=NOW)
    assert result.status is TemporalTruthStatus.WATCH
    assert any(reason.startswith("RETROACTIVE_CORRECTION_AGE_EXCEEDED") for reason in result.reasons)


def test_kickoff_correction_requires_human_review():
    v1, v2, _ = chain()
    corrected_fixture = replace(v2.snapshot.fixture, kickoff_utc=v2.snapshot.fixture.kickoff_utc + timedelta(minutes=5))
    s3 = replace(v2.snapshot, snapshot_id="kickoff-fix", observed_at=NOW - timedelta(minutes=10), fixture=corrected_fixture)
    v3 = version(
        "v3", snap=s3, known_at=s3.observed_at, valid_from=v2.valid_from_event_time,
        kind=TruthRevisionKind.CORRECTION, supersedes="v2", correction_scope=("KICKOFF_UTC",),
        reason_code="KICKOFF_CORRECTION", human_reviewed=False,
    )
    result = assess_truth_chain((v1, v2, v3), policy=policy(), now=NOW)
    assert any(reason.startswith("CRITICAL_CORRECTION_NOT_HUMAN_REVIEWED") for reason in result.reasons)


# ----- bitemporal point-in-time truth -----

def test_query_before_correction_uses_v2_not_future_correction():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW - timedelta(minutes=15), event_time=NOW - timedelta(minutes=15), now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.PASS
    assert result.selected_version_id == "v2"
    assert result.future_knowledge_used is False


def test_query_after_correction_reconstructs_corrected_past():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW - timedelta(minutes=5), event_time=NOW - timedelta(minutes=15), now=NOW, policy=policy(),
    )
    assert result.selected_version_id == "v3"
    assert result.retrospective_correction_applied is True
    assert result.status is TemporalTruthStatus.WATCH


def test_query_before_any_truth_blocks():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW - timedelta(minutes=40), event_time=NOW - timedelta(minutes=40), now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.BLOCK
    assert "NO_TRUTH_KNOWN_AS_OF_QUERY" in result.reasons


def test_query_from_future_blocks():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW + timedelta(seconds=1), event_time=NOW, now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.BLOCK
    assert "AS_OF_FROM_FUTURE" in result.reasons


def test_query_wrong_provider_fails_closed():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-x", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW, event_time=NOW, now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.BLOCK


def test_invalid_chain_blocks_point_in_time_query():
    v1, v2, v3 = chain()
    bad = replace(v3, supersedes_version_id="v1")
    result = resolve_point_in_time_truth(
        (v1, v2, bad), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW, event_time=NOW, now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.BLOCK
    assert "TRUTH_CHAIN_INVALID" in result.reasons


def test_event_time_cutoff_prevents_using_later_progression():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW - timedelta(minutes=15), event_time=NOW - timedelta(minutes=25), now=NOW, policy=policy(),
    )
    assert result.selected_version_id == "v1"


def test_current_query_uses_chain_head_when_applicable():
    result = resolve_point_in_time_truth(
        chain(), provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        as_of=NOW, event_time=NOW, now=NOW, policy=policy(),
    )
    assert result.selected_version_id == "v3"


# ----- decision freeze / leakage prevention -----

def test_valid_decision_freeze_passes_even_after_later_correction():
    result = validate_decision_evidence_freeze(freeze_for_v2(), chain(), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.PASS
    assert result.temporal_leakage_detected is False


def test_freeze_using_future_correction_is_blocked():
    v1, v2, v3 = chain()
    freeze = freeze_for_v2(
        v3,
        decision_at=NOW - timedelta(minutes=15),
        truth_version_id="v3",
        truth_version_fingerprint=v3.fingerprint,
        snapshot_fingerprint=v3.snapshot.fingerprint,
    )
    result = validate_decision_evidence_freeze(freeze, (v1, v2, v3), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.BLOCK
    assert "FUTURE_KNOWLEDGE_IN_DECISION_EVIDENCE" in result.reasons


def test_freeze_fingerprint_mismatch_blocks():
    freeze = replace(freeze_for_v2(), truth_version_fingerprint="c" * 64)
    result = validate_decision_evidence_freeze(freeze, chain(), now=NOW, policy=policy())
    assert "FROZEN_TRUTH_FINGERPRINT_MISMATCH" in result.reasons


def test_freeze_snapshot_fingerprint_mismatch_blocks():
    freeze = replace(freeze_for_v2(), snapshot_fingerprint="c" * 64)
    result = validate_decision_evidence_freeze(freeze, chain(), now=NOW, policy=policy())
    assert "FROZEN_SNAPSHOT_FINGERPRINT_MISMATCH" in result.reasons


def test_freeze_unknown_version_blocks():
    freeze = replace(freeze_for_v2(), truth_version_id="missing")
    result = validate_decision_evidence_freeze(freeze, chain(), now=NOW, policy=policy())
    assert "FROZEN_TRUTH_VERSION_NOT_UNIQUE" in result.reasons


def test_freeze_old_version_when_newer_truth_known_blocks():
    v1, v2, v3 = chain()
    freeze = DecisionEvidenceFreeze(
        decision_id="decision-old", provider_id=v1.provider_id, canonical_fixture_id=v1.canonical_fixture_id,
        decision_at=NOW - timedelta(minutes=15), truth_version_id="v1", truth_version_fingerprint=v1.fingerprint,
        snapshot_fingerprint=v1.snapshot.fingerprint, model_version="m", market_key=None, evidence_sha256="d" * 64,
    )
    result = validate_decision_evidence_freeze(freeze, (v1, v2, v3), now=NOW, policy=policy())
    assert "DECISION_DID_NOT_USE_LATEST_KNOWN_TRUTH" in result.reasons


def test_future_decision_time_blocks():
    freeze = replace(freeze_for_v2(), decision_at=NOW + timedelta(minutes=1))
    result = validate_decision_evidence_freeze(freeze, chain(), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.BLOCK


# ----- post-decision impact and correction gate -----

def test_post_decision_score_correction_is_high_impact_watch():
    result = assess_post_decision_revision_impact(freeze_for_v2(), chain(), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.WATCH
    assert result.impact_level is RevisionImpactLevel.HIGH
    assert result.reanalysis_required is True
    assert result.original_analysis_quality_determined is False


def test_no_post_decision_correction_is_pass():
    v1, v2, _ = chain()
    result = assess_post_decision_revision_impact(freeze_for_v2(v2), (v1, v2), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.PASS
    assert result.impact_level is RevisionImpactLevel.NONE


def test_stat_correction_is_medium_impact():
    v1, v2, _ = chain()
    s3 = replace(
        v2.snapshot, snapshot_id="stat-fix", observed_at=NOW - timedelta(minutes=10),
        statistics=(StatisticValue("shots", 7, 4), StatisticValue("corners", 3, 1)),
    )
    v3 = version(
        "v3", snap=s3, known_at=s3.observed_at, valid_from=v2.valid_from_event_time,
        kind=TruthRevisionKind.CORRECTION, supersedes="v2", correction_scope=("STAT:shots",),
        reason_code="STAT_CORRECTION",
    )
    result = assess_post_decision_revision_impact(freeze_for_v2(v2), (v1, v2, v3), now=NOW, policy=policy())
    assert result.impact_level is RevisionImpactLevel.MEDIUM


def test_invalid_freeze_causes_critical_impact_block():
    bad_freeze = replace(freeze_for_v2(), truth_version_fingerprint="c" * 64)
    result = assess_post_decision_revision_impact(bad_freeze, chain(), now=NOW, policy=policy())
    assert result.status is TemporalTruthStatus.BLOCK
    assert result.impact_level is RevisionImpactLevel.CRITICAL


def test_correction_gate_watch_requires_reanalysis_for_score_correction():
    result = evaluate_provider_correction_gate(chain(), policy=policy(), now=NOW, decision_freeze=freeze_for_v2())
    assert result.status is TemporalTruthStatus.WATCH
    assert result.controlled_reanalysis_required is True
    assert result.historical_backfill_allowed is False
    assert result.automatic_wagering is False


def test_correction_gate_passes_clean_chain_without_decision():
    v1, v2, _ = chain()
    result = evaluate_provider_correction_gate((v1, v2), policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.PASS


def test_correction_gate_blocks_invalid_chain():
    v1, v2, v3 = chain()
    result = evaluate_provider_correction_gate((v1, v2, replace(v3, human_reviewed=False)), policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.BLOCK


# ----- training / backtest temporal cutoff -----

def test_training_cutoff_uses_truth_known_at_feature_time():
    result = build_training_truth_cutoff(
        sample_id="sample-1", provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        feature_cutoff_at=NOW - timedelta(minutes=15), label_cutoff_at=NOW,
        versions=chain(), now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.PASS
    assert result.selected_feature_truth_fingerprint == chain()[1].fingerprint
    assert result.leakage_detected is False


def test_training_cutoff_does_not_use_later_correction():
    result = build_training_truth_cutoff(
        sample_id="sample-1", provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        feature_cutoff_at=NOW - timedelta(minutes=15), label_cutoff_at=NOW,
        versions=chain(), now=NOW, policy=policy(),
    )
    assert result.selected_feature_truth_fingerprint != chain()[2].fingerprint


def test_training_cutoff_blocks_when_no_feature_truth_exists():
    result = build_training_truth_cutoff(
        sample_id="sample-1", provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        feature_cutoff_at=NOW - timedelta(minutes=45), label_cutoff_at=NOW,
        versions=chain(), now=NOW, policy=policy(),
    )
    assert result.status is TemporalTruthStatus.BLOCK
    assert result.leakage_detected is True


def test_training_label_cutoff_may_be_later_than_feature_cutoff():
    result = build_training_truth_cutoff(
        sample_id="sample-1", provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
        feature_cutoff_at=NOW - timedelta(minutes=15), label_cutoff_at=NOW,
        versions=chain(), now=NOW, policy=policy(),
    )
    assert result.label_cutoff_at == NOW


def test_training_label_cutoff_before_feature_cutoff_rejected():
    with pytest.raises(ValueError):
        build_training_truth_cutoff(
            sample_id="sample-1", provider_id="provider-a", canonical_fixture_id=fixture().canonical_fixture_id,
            feature_cutoff_at=NOW, label_cutoff_at=NOW - timedelta(seconds=1),
            versions=chain(), now=NOW, policy=policy(),
        )


# ----- append-only provider revision ledger -----

def test_empty_revision_ledger_verifies(tmp_path):
    ok, count, head, ids = verify_provider_revision_ledger(tmp_path / "ledger.jsonl")
    assert (ok, count, head, ids) == (True, 0, GENESIS, ())


def test_revision_ledger_appends_and_verifies(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    v1, v2, _ = chain()
    h1 = ledger.append(v1)
    h2 = ledger.append(v2)
    ok, count, head, ids = verify_provider_revision_ledger(path)
    assert ok is True
    assert count == 2
    assert head == h2 and h1 != h2
    assert ids == ("v1", "v2")


def test_revision_ledger_rejects_duplicate_version_id(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    v1 = chain()[0]
    ledger.append(v1)
    with pytest.raises(RuntimeError):
        ledger.append(v1)


def test_revision_ledger_detects_payload_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    ledger.append(chain()[0])
    rows = path.read_text().splitlines()
    row = json.loads(rows[0])
    row["payload"]["provider_id"] = "tampered"
    path.write_text(json.dumps(row) + "\n")
    assert verify_provider_revision_ledger(path)[0] is False


def test_revision_ledger_detects_hash_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    ledger.append(chain()[0])
    row = json.loads(path.read_text())
    row["hash"] = "f" * 64
    path.write_text(json.dumps(row) + "\n")
    assert verify_provider_revision_ledger(path)[0] is False


def test_revision_ledger_refuses_append_after_corruption(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    v1, v2, _ = chain()
    ledger.append(v1)
    path.write_text(path.read_text().replace('"provider_id":"provider-a"', '"provider_id":"provider-z"'))
    with pytest.raises(RuntimeError):
        ledger.append(v2)


def test_revision_ledger_chain_detects_deleted_first_row(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    v1, v2, _ = chain()
    ledger.append(v1)
    ledger.append(v2)
    lines = path.read_text().splitlines()
    path.write_text(lines[1] + "\n")
    assert verify_provider_revision_ledger(path)[0] is False


def test_revision_ledger_writes_lock_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ProviderRevisionLedger(path)
    ledger.append(chain()[0])
    assert path.with_suffix(".jsonl.lock").exists()
