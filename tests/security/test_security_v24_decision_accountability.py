from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from hashlib import sha256

import pytest

from app.security.accountability_ledger import (
    AccountabilityLearningLedger,
    GENESIS,
    verify_accountability_ledger,
)
from app.security.analysis_accountability import (
    AnalysisAccountabilityAssessment,
    AttributionCategory,
    CoverageState,
    DecisionOperationalContext,
    DecisionOutcomeEvidence,
    EntryTimingState,
    SettledOutcome,
    assess_analysis_accountability,
)
from app.security.decision_replay import DecisionReplayResult, replay_decision_as_known
from app.security.learning_integrity import (
    IndependentLearningReview,
    LearningDisposition,
    LearningIntegrityResult,
    evaluate_learning_integrity,
)
from app.security.provider_normalization import CanonicalFixtureIdentity
from app.security.provider_reconciliation import (
    EventState,
    MarketIdentity,
    ProviderEventSnapshot,
    StatisticValue,
)
from app.security.provider_temporal_truth import (
    DecisionEvidenceFreeze,
    ProviderTruthVersion,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    TruthRevisionKind,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 19, 2, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def fixture():
    return CanonicalFixtureIdentity(
        sport="football",
        canonical_fixture_id="fixture:matrix:1",
        competition_id="competition:1",
        home_entity_id="team:home",
        away_entity_id="team:away",
        kickoff_utc=datetime(2026, 8, 19, 0, 0, tzinfo=UTC),
    )


def market():
    return MarketIdentity("TOTAL_GOALS", "FULL_TIME", "OVER", 2500)


def snapshot(snapshot_id, observed_at, event_time, *, home_score=0, state=EventState.LIVE):
    return ProviderEventSnapshot(
        snapshot_id=snapshot_id,
        provider_id="provider-a",
        provider_fixture_id="external-1",
        fixture=fixture(),
        observed_at=observed_at,
        event_time=event_time,
        state=state,
        home_score=home_score,
        away_score=0,
        statistics=(StatisticValue("shots", 8, 4), StatisticValue("corners", 3, 1)),
        available_markets=(market(),),
    )


def version(version_id, snap, kind, supersedes=None, *, scope=(), reason=None, reviewed=False):
    return ProviderTruthVersion(
        version_id=version_id,
        provider_id="provider-a",
        canonical_fixture_id="fixture:matrix:1",
        provider_fixture_id="external-1",
        snapshot=snap,
        known_at=snap.observed_at,
        valid_from_event_time=snap.event_time,
        revision_kind=kind,
        supersedes_version_id=supersedes,
        correction_scope=tuple(scope),
        reason_code=reason,
        evidence_sha256=SHA_A,
        human_reviewed=reviewed,
    )


def truth_chain(*, with_correction=True):
    s1 = snapshot("s1", NOW - timedelta(minutes=110), NOW - timedelta(minutes=110))
    v1 = version("v1", s1, TruthRevisionKind.INITIAL)
    s2 = snapshot("s2", NOW - timedelta(minutes=100), NOW - timedelta(minutes=100), home_score=1)
    v2 = version("v2", s2, TruthRevisionKind.PROGRESSION, "v1")
    if not with_correction:
        return (v1, v2)
    s3 = snapshot("s3", NOW - timedelta(minutes=80), NOW - timedelta(minutes=100), home_score=0)
    v3 = version(
        "v3", s3, TruthRevisionKind.CORRECTION, "v2",
        scope=("HOME_SCORE",), reason="PROVIDER_SCORE_CORRECTION", reviewed=True,
    )
    return (v1, v2, v3)


def policy():
    return TemporalTruthPolicy(
        max_recording_delay_seconds=60,
        correction_review_age_seconds=3600,
        require_human_review_for_critical_correction=True,
    )


def freeze(*, truth=None, decision_id="decision-1", market_key=None):
    truth = truth or truth_chain()[1]
    return DecisionEvidenceFreeze(
        decision_id=decision_id,
        provider_id=truth.provider_id,
        canonical_fixture_id=truth.canonical_fixture_id,
        decision_at=NOW - timedelta(minutes=90),
        truth_version_id=truth.version_id,
        truth_version_fingerprint=truth.fingerprint,
        snapshot_fingerprint=truth.snapshot.fingerprint,
        model_version="model-v1",
        market_key=market_key if market_key is not None else market().key,
        evidence_sha256=SHA_B,
    )


def outcome(*, decision_id="decision-1", result=SettledOutcome.LOSS, verified=True, market_key=None, settled_at=None):
    return DecisionOutcomeEvidence(
        decision_id=decision_id,
        market_key=market_key if market_key is not None else market().key,
        outcome=result,
        settled_at=settled_at or NOW - timedelta(minutes=10),
        settlement_verified=verified,
        settlement_evidence_sha256=SHA_C,
    )


def context(*, decision_id="decision-1", coverage=CoverageState.COMPLETE, timing=EntryTimingState.ON_TIME,
            data_quality=True, market_ok=True, execution_ok=True, captured_at=None):
    return DecisionOperationalContext(
        decision_id=decision_id,
        captured_at=captured_at or NOW - timedelta(minutes=95),
        coverage_state=coverage,
        entry_timing_state=timing,
        data_quality_gate_passed=data_quality,
        market_identity_verified=market_ok,
        execution_matches_recommendation=execution_ok,
        context_evidence_sha256=SHA_D,
    )


def assessment(*, chain=None, out=None, ctx=None, fr=None):
    chain = tuple(chain or truth_chain(with_correction=False))
    fr = fr or freeze(truth=chain[1])
    return assess_analysis_accountability(
        fr,
        chain,
        out or outcome(),
        ctx or context(),
        policy=policy(),
        now=NOW,
    )


def review_for(a, disposition, *, owner="owner-1", reviewer="reviewer-2", independent=True, reviewed_at=None):
    return IndependentLearningReview(
        review_id="review-1",
        decision_id=a.decision_id,
        assessment_fingerprint=a.fingerprint,
        decision_owner_id=owner,
        reviewer_id=reviewer,
        reviewed_at=reviewed_at or NOW - timedelta(minutes=1),
        disposition=disposition,
        review_evidence_sha256=SHA_A,
        independent_review=independent,
    )


# ----- decision replay -----

def test_replay_exact_frozen_evidence_passes():
    chain = truth_chain()
    result = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.PASS
    assert result.selected_truth_version_id == "v2"
    assert result.exact_frozen_evidence_reproduced is True
    assert result.future_knowledge_used is False


def test_replay_ignores_later_provider_correction():
    chain = truth_chain()
    result = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    assert result.selected_truth_version_id == "v2"
    assert result.selected_truth_version_id != "v3"


def test_replay_fingerprint_is_deterministic():
    chain = truth_chain()
    a = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    b = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    assert a.fingerprint == b.fingerprint


def test_replay_blocks_tampered_truth_fingerprint():
    chain = truth_chain()
    fr = replace(freeze(truth=chain[1]), truth_version_fingerprint="f" * 64)
    result = replay_decision_as_known(fr, chain, policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.BLOCK
    assert result.future_knowledge_used is True


def test_replay_blocks_tampered_snapshot_fingerprint():
    chain = truth_chain()
    fr = replace(freeze(truth=chain[1]), snapshot_fingerprint="f" * 64)
    assert replay_decision_as_known(fr, chain, policy=policy(), now=NOW).status is TemporalTruthStatus.BLOCK


def test_replay_blocks_missing_frozen_version():
    chain = truth_chain()
    fr = freeze(truth=chain[1])
    assert replay_decision_as_known(fr, (chain[0], chain[2]), policy=policy(), now=NOW).status is TemporalTruthStatus.BLOCK


def test_replay_blocks_decision_that_did_not_use_latest_known_truth():
    chain = truth_chain()
    fr = freeze(truth=chain[0])
    fr = replace(fr, decision_at=NOW - timedelta(minutes=90))
    result = replay_decision_as_known(fr, chain, policy=policy(), now=NOW)
    assert result.status is TemporalTruthStatus.BLOCK


def test_replay_blocks_future_decision():
    chain = truth_chain()
    fr = replace(freeze(truth=chain[1]), decision_at=NOW + timedelta(seconds=1))
    assert replay_decision_as_known(fr, chain, policy=policy(), now=NOW).status is TemporalTruthStatus.BLOCK


def test_replay_result_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        DecisionReplayResult("d", TemporalTruthStatus.PASS, (), SHA_A, "v1", SHA_B, SHA_C,
                             datetime(2026, 8, 19, 2, 0), False, True)


def test_replay_result_rejects_auto_model_promotion():
    chain = truth_chain()
    r = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    with pytest.raises(ValueError):
        replace(r, automatic_model_promotion=True)


def test_replay_result_rejects_auto_wagering():
    chain = truth_chain()
    r = replay_decision_as_known(freeze(truth=chain[1]), chain, policy=policy(), now=NOW)
    with pytest.raises(ValueError):
        replace(r, automatic_wagering=True)


# ----- outcome/context construction -----

def test_unsettled_outcome_may_not_be_verified():
    with pytest.raises(ValueError):
        outcome(result=SettledOutcome.UNSETTLED, verified=True)


def test_outcome_rejects_bad_sha():
    with pytest.raises(ValueError):
        replace(outcome(), settlement_evidence_sha256="bad")


def test_context_rejects_bad_sha():
    with pytest.raises(ValueError):
        replace(context(), context_evidence_sha256="bad")


def test_outcome_fingerprint_deterministic():
    assert outcome().fingerprint == outcome().fingerprint


def test_context_fingerprint_deterministic():
    assert context().fingerprint == context().fingerprint


# ----- accountability attribution -----

def test_clean_loss_is_signal_error_candidate_not_conviction():
    a = assessment()
    assert a.status is TemporalTruthStatus.WATCH
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE in a.candidate_attributions
    assert a.analysis_quality_determined is False
    assert a.learning_label_allowed is False


def test_clean_win_does_not_prove_analysis_quality():
    a = assessment(out=outcome(result=SettledOutcome.WIN))
    assert a.status is TemporalTruthStatus.PASS
    assert a.candidate_attributions == (AttributionCategory.NO_PERFORMANCE_JUDGMENT,)
    assert a.analysis_quality_determined is False


def test_push_has_no_performance_judgment():
    a = assessment(out=outcome(result=SettledOutcome.PUSH))
    assert AttributionCategory.NO_PERFORMANCE_JUDGMENT in a.candidate_attributions


def test_void_has_no_performance_judgment():
    a = assessment(out=outcome(result=SettledOutcome.VOID))
    assert AttributionCategory.NO_PERFORMANCE_JUDGMENT in a.candidate_attributions


def test_unsettled_is_unresolved_watch():
    a = assessment(out=outcome(result=SettledOutcome.UNSETTLED, verified=False))
    assert a.status is TemporalTruthStatus.WATCH
    assert AttributionCategory.UNRESOLVED in a.candidate_attributions


def test_unverified_settlement_blocks():
    a = assessment(out=outcome(verified=False))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.SETTLEMENT_EVIDENCE_GAP in a.candidate_attributions


def test_settlement_before_decision_blocks():
    a = assessment(out=outcome(settled_at=NOW - timedelta(minutes=100)))
    assert a.status is TemporalTruthStatus.BLOCK


def test_settlement_from_future_blocks():
    a = assessment(out=outcome(settled_at=NOW + timedelta(minutes=1)))
    assert a.status is TemporalTruthStatus.BLOCK


def test_decision_scope_mismatch_blocks():
    a = assessment(out=outcome(decision_id="other"))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.DATA_INTEGRITY_FAILURE in a.candidate_attributions


def test_outcome_market_mismatch_blocks():
    a = assessment(out=outcome(market_key="TOTAL_GOALS|FULL_TIME|OVER|3500"))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.MARKET_IDENTITY_MISMATCH in a.candidate_attributions


def test_unverified_market_identity_blocks():
    a = assessment(ctx=context(market_ok=False))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.MARKET_IDENTITY_MISMATCH in a.candidate_attributions


def test_execution_mismatch_blocks_analysis_attribution():
    a = assessment(ctx=context(execution_ok=False))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.EXECUTION_MISMATCH in a.candidate_attributions


def test_partial_coverage_is_separate_candidate():
    a = assessment(ctx=context(coverage=CoverageState.PARTIAL))
    assert a.status is TemporalTruthStatus.WATCH
    assert AttributionCategory.DATA_COVERAGE_GAP in a.candidate_attributions
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE not in a.candidate_attributions


def test_missing_coverage_is_separate_candidate():
    a = assessment(ctx=context(coverage=CoverageState.MISSING))
    assert AttributionCategory.DATA_COVERAGE_GAP in a.candidate_attributions
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE not in a.candidate_attributions


def test_failed_data_quality_is_separate_candidate():
    a = assessment(ctx=context(data_quality=False))
    assert AttributionCategory.DATA_QUALITY_AT_DECISION in a.candidate_attributions
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE not in a.candidate_attributions


def test_late_entry_is_separate_candidate():
    a = assessment(ctx=context(timing=EntryTimingState.LATE))
    assert AttributionCategory.ENTRY_TIMING_ISSUE in a.candidate_attributions
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE not in a.candidate_attributions


def test_missed_entry_is_separate_candidate():
    a = assessment(ctx=context(timing=EntryTimingState.MISSED))
    assert AttributionCategory.ENTRY_TIMING_ISSUE in a.candidate_attributions


def test_post_decision_provider_correction_is_separate_candidate():
    chain = truth_chain(with_correction=True)
    a = assessment(chain=chain, fr=freeze(truth=chain[1]))
    assert a.status is TemporalTruthStatus.WATCH
    assert AttributionCategory.PROVIDER_CORRECTION_AFTER_DECISION in a.candidate_attributions
    assert AttributionCategory.SIGNAL_ERROR_CANDIDATE not in a.candidate_attributions
    assert a.controlled_reanalysis_required is True


def test_future_context_evidence_blocks():
    a = assessment(ctx=context(captured_at=NOW - timedelta(minutes=80)))
    assert a.status is TemporalTruthStatus.BLOCK
    assert AttributionCategory.DATA_INTEGRITY_FAILURE in a.candidate_attributions


def test_accountability_fingerprint_is_deterministic():
    assert assessment().fingerprint == assessment().fingerprint


def test_accountability_rejects_automatic_quality_judgment():
    a = assessment()
    with pytest.raises(ValueError):
        replace(a, analysis_quality_determined=True)


def test_accountability_rejects_pre_review_learning_label():
    a = assessment()
    with pytest.raises(ValueError):
        replace(a, learning_label_allowed=True)


def test_accountability_rejects_auto_model_promotion():
    with pytest.raises(ValueError):
        replace(assessment(), automatic_model_promotion=True)


def test_accountability_rejects_auto_wagering():
    with pytest.raises(ValueError):
        replace(assessment(), automatic_wagering=True)


# ----- independent learning integrity -----

def test_confirmed_signal_error_requires_matching_candidate_and_independent_review():
    a = assessment()
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_model_error_dataset is True
    assert r.eligible_for_process_improvement_dataset is False


def test_signal_error_label_not_supported_by_partial_coverage_case():
    a = assessment(ctx=context(coverage=CoverageState.PARTIAL))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.BLOCK
    assert r.eligible_for_model_error_dataset is False


def test_data_quality_error_routes_to_process_dataset():
    a = assessment(ctx=context(data_quality=False))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_DATA_QUALITY_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_process_improvement_dataset is True
    assert r.eligible_for_model_error_dataset is False


def test_coverage_error_routes_to_process_dataset():
    a = assessment(ctx=context(coverage=CoverageState.PARTIAL))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_DATA_COVERAGE_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_process_improvement_dataset is True


def test_timing_error_routes_to_process_dataset():
    a = assessment(ctx=context(timing=EntryTimingState.LATE))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_TIMING_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_process_improvement_dataset is True


def test_provider_revision_routes_to_process_dataset():
    chain = truth_chain(with_correction=True)
    a = assessment(chain=chain, fr=freeze(truth=chain[1]))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_PROVIDER_REVISION_IMPACT), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_process_improvement_dataset is True


def test_execution_error_can_be_process_learning_but_not_model_error():
    a = assessment(ctx=context(execution_ok=False))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_EXECUTION_ERROR), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert r.eligible_for_process_improvement_dataset is True
    assert r.eligible_for_model_error_dataset is False


def test_inconclusive_review_emits_no_learning_label():
    a = assessment()
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.INCONCLUSIVE), now=NOW)
    assert r.status is TemporalTruthStatus.WATCH
    assert not r.eligible_for_model_error_dataset
    assert not r.eligible_for_process_improvement_dataset


def test_no_action_emits_no_learning_label():
    a = assessment(out=outcome(result=SettledOutcome.WIN))
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.NO_ACTION), now=NOW)
    assert r.status is TemporalTruthStatus.PASS
    assert not r.eligible_for_model_error_dataset
    assert not r.eligible_for_process_improvement_dataset


def test_non_independent_review_blocks():
    a = assessment()
    rv = review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR, independent=False)
    r = evaluate_learning_integrity(a, rv, now=NOW)
    assert r.status is TemporalTruthStatus.BLOCK


def test_independent_self_review_rejected_at_construction():
    a = assessment()
    with pytest.raises(ValueError):
        review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR, owner="same", reviewer="same", independent=True)


def test_review_assessment_fingerprint_mismatch_blocks():
    a = assessment()
    rv = replace(review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), assessment_fingerprint="f" * 64)
    assert evaluate_learning_integrity(a, rv, now=NOW).status is TemporalTruthStatus.BLOCK


def test_review_decision_scope_mismatch_blocks():
    a = assessment()
    rv = replace(review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), decision_id="other")
    assert evaluate_learning_integrity(a, rv, now=NOW).status is TemporalTruthStatus.BLOCK


def test_future_review_blocks():
    a = assessment()
    rv = review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR, reviewed_at=NOW + timedelta(seconds=1))
    assert evaluate_learning_integrity(a, rv, now=NOW).status is TemporalTruthStatus.BLOCK


def test_untrusted_data_integrity_case_cannot_enter_learning_dataset():
    a = assessment(out=outcome(decision_id="other"))
    rv = review_for(a, LearningDisposition.INCONCLUSIVE)
    r = evaluate_learning_integrity(a, rv, now=NOW)
    assert r.status is TemporalTruthStatus.BLOCK


def test_unverified_settlement_case_cannot_enter_learning_dataset():
    a = assessment(out=outcome(verified=False))
    rv = review_for(a, LearningDisposition.INCONCLUSIVE)
    assert evaluate_learning_integrity(a, rv, now=NOW).status is TemporalTruthStatus.BLOCK


def test_learning_result_rejects_auto_model_promotion():
    a = assessment()
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)
    with pytest.raises(ValueError):
        replace(r, automatic_model_promotion=True)


def test_learning_result_rejects_auto_wagering():
    a = assessment()
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)
    with pytest.raises(ValueError):
        replace(r, automatic_wagering=True)


def test_learning_result_fingerprint_is_deterministic():
    a = assessment()
    rv = review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR)
    assert evaluate_learning_integrity(a, rv, now=NOW).fingerprint == evaluate_learning_integrity(a, rv, now=NOW).fingerprint


# ----- accountability ledger -----

def model_learning_result():
    a = assessment()
    return evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)


def test_missing_accountability_ledger_is_valid(tmp_path):
    ok, count, previous, ids = verify_accountability_ledger(tmp_path / "missing.jsonl")
    assert (ok, count, previous, ids) == (True, 0, GENESIS, ())


def test_accountability_ledger_append_and_verify(tmp_path):
    path = tmp_path / "ledger.jsonl"
    digest = AccountabilityLearningLedger(path).append(model_learning_result())
    ok, count, previous, ids = verify_accountability_ledger(path)
    assert ok is True
    assert count == 1
    assert previous == digest
    assert ids == ("decision-1",)


def test_accountability_ledger_rejects_duplicate_decision(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = AccountabilityLearningLedger(path)
    result = model_learning_result()
    ledger.append(result)
    with pytest.raises(RuntimeError):
        ledger.append(result)


def test_accountability_ledger_detects_payload_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    AccountabilityLearningLedger(path).append(model_learning_result())
    row = json.loads(path.read_text().strip())
    row["payload"]["status"] = "BLOCK"
    path.write_text(json.dumps(row, separators=(",", ":")) + "\n")
    assert verify_accountability_ledger(path)[0] is False


def test_accountability_ledger_refuses_append_after_corruption(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"bad":true}\n')
    with pytest.raises(RuntimeError):
        AccountabilityLearningLedger(path).append(model_learning_result())


def test_accountability_ledger_detects_invalid_json(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("not-json\n")
    assert verify_accountability_ledger(path)[0] is False


def test_accountability_ledger_ignores_blank_lines(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n\n")
    assert verify_accountability_ledger(path) == (True, 0, GENESIS, ())


def test_accountability_ledger_hash_depends_on_payload(tmp_path):
    result = model_learning_result()
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    h1 = AccountabilityLearningLedger(p1).append(result)
    changed = replace(result, disposition=LearningDisposition.NO_ACTION,
                      eligible_for_model_error_dataset=False,
                      eligible_for_process_improvement_dataset=False)
    h2 = AccountabilityLearningLedger(p2).append(changed)
    assert h1 != h2


def test_manual_wrong_previous_hash_is_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    payload = json.loads(json.dumps({"decision_id": "d"}))
    row = {"previous_hash": "1" * 64, "payload": payload, "hash": sha256(("1" * 64).encode() + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    path.write_text(json.dumps(row) + "\n")
    assert verify_accountability_ledger(path)[0] is False


def test_learning_result_block_cannot_claim_eligibility():
    a = assessment()
    r = evaluate_learning_integrity(a, review_for(a, LearningDisposition.CONFIRMED_SIGNAL_ERROR), now=NOW)
    with pytest.raises(ValueError):
        replace(r, status=TemporalTruthStatus.BLOCK)
