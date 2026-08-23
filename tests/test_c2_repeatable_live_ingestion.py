from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from app.application.football.repeatable_live_ingestion import (
    ADMISSION_BLOCKED,
    ADMISSION_ELIGIBLE_REVIEW,
    ADMISSION_OBSERVE_ONLY,
    ALIGNMENT_BLOCKED,
    ALIGNMENT_OBSERVE_ONLY,
    FRESHNESS_BLOCKED,
    FRESHNESS_OBSERVE_ONLY,
    FRESHNESS_PASS,
    FootballLiveFreshnessPolicy,
    SQLiteFootballLiveObservationStore,
    evaluate_football_cross_modal_alignment,
    evaluate_football_live_freshness,
    evaluate_repeatable_football_live_admission,
)
from app.core.live_temporal_observation import (
    build_live_temporal_observation,
)


BASE = datetime(2026, 8, 23, 16, tzinfo=UTC)


def observation(
    *,
    modality="fixture_events",
    sequence_id=1,
    observed_offset_ms=0,
    correlation_id="a" * 64,
    subject_key="fixture:1557375",
):
    observed = BASE + timedelta(milliseconds=observed_offset_ms)
    return build_live_temporal_observation(
        sport="football",
        subject_key=subject_key,
        modality=modality,
        correlation_id=correlation_id,
        sequence_id=sequence_id,
        observed_at=observed,
        request_started_at=observed + timedelta(milliseconds=20),
        response_received_at=observed + timedelta(milliseconds=40),
        ingested_at=observed + timedelta(milliseconds=60),
        normalized_at=observed + timedelta(milliseconds=80),
        feature_ready_at=observed + timedelta(milliseconds=100),
        source_record_fingerprint=(
            f"{sequence_id:064x}"[-64:]
        ),
    )


def calibrated_policy(**overrides):
    values = dict(
        fixture_status_max_source_age_ms=500,
        fixture_statistics_max_source_age_ms=500,
        fixture_events_max_source_age_ms=500,
        odds_max_source_age_ms=500,
        max_ingestion_to_normalization_ms=500,
        max_normalization_to_feature_ms=500,
        max_cross_modal_skew_ms=500,
    )
    values.update(overrides)
    return FootballLiveFreshnessPolicy(**values)


def test_default_policy_never_invents_thresholds_and_is_observe_only():
    policy = FootballLiveFreshnessPolicy()
    decision = evaluate_football_live_freshness(
        observation(),
        policy,
    )

    assert policy.thresholds_empirically_calibrated is False
    assert policy.production_admissible is False
    assert decision.status == FRESHNESS_OBSERVE_ONLY
    assert "SOURCE_AGE_THRESHOLD_UNCALIBRATED" in decision.reason_codes


def test_explicit_policy_can_pass_without_becoming_production_policy():
    decision = evaluate_football_live_freshness(
        observation(),
        calibrated_policy(),
    )

    assert decision.status == FRESHNESS_PASS
    assert decision.production_admissible is False
    assert decision.model_decision_run is False


def test_stale_input_fails_closed():
    item = observation()
    policy = calibrated_policy(
        fixture_events_max_source_age_ms=50,
    )
    decision = evaluate_football_live_freshness(item, policy)

    assert decision.status == FRESHNESS_BLOCKED
    assert "SOURCE_AGE_EXCEEDED" in decision.reason_codes


def test_alignment_without_calibrated_tolerance_is_observe_only():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=100,
        ),
    )
    decision = evaluate_football_cross_modal_alignment(
        items,
        FootballLiveFreshnessPolicy(),
    )

    assert decision.status == ALIGNMENT_OBSERVE_ONLY
    assert decision.synchronous_snapshot is False
    assert decision.max_observed_at_skew_ms == 100


def test_cross_modal_skew_exceedance_blocks_fusion():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=600,
        ),
    )
    decision = evaluate_football_cross_modal_alignment(
        items,
        calibrated_policy(max_cross_modal_skew_ms=500),
    )

    assert decision.status == ALIGNMENT_BLOCKED
    assert "CROSS_MODAL_SKEW_EXCEEDED" in decision.reason_codes


def test_cross_modal_identity_or_correlation_mismatch_blocks():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            correlation_id="b" * 64,
        ),
    )
    decision = evaluate_football_cross_modal_alignment(
        items,
        calibrated_policy(),
    )

    assert decision.status == ALIGNMENT_BLOCKED
    assert "CORRELATION_ID_MISMATCH" in decision.reason_codes


def test_sequence_store_is_idempotent_and_quarantines_out_of_order(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")

    one = observation(sequence_id=1)
    three = observation(sequence_id=3)
    two = observation(sequence_id=2)

    first = store.record(one)
    repeated = store.record(one)
    third = store.record(three)
    late = store.record(two)

    assert first.status == "ACCEPTED"
    assert repeated.idempotent is True
    assert third.status == "ACCEPTED"
    assert late.status == "QUARANTINED_OUT_OF_ORDER"
    assert late.accepted_for_fusion is False
    assert store.audit_integrity() is True


def test_same_sequence_cannot_silently_mutate(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    first = observation(sequence_id=1)
    store.record(first)

    mutated = build_live_temporal_observation(
        sport="football",
        subject_key=first.subject_key,
        modality=first.modality,
        correlation_id=first.correlation_id,
        sequence_id=first.sequence_id,
        observed_at=first.observed_at,
        request_started_at=first.request_started_at,
        response_received_at=first.response_received_at,
        ingested_at=first.ingested_at,
        normalized_at=first.normalized_at,
        feature_ready_at=first.feature_ready_at + timedelta(milliseconds=1),
        source_record_fingerprint="f" * 64,
    )

    with pytest.raises(ValueError, match="LIVE_SEQUENCE_MUTATION_VIOLATION"):
        store.record(mutated)


def test_store_integrity_detects_payload_tampering(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    item = observation()
    store.record(item)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET payload_json = ?
            WHERE observation_fingerprint = ?
            """,
            ("{}\n", item.observation_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_repeatable_admission_is_observe_only_until_policy_is_explicit():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=100,
        ),
    )
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=FootballLiveFreshnessPolicy(),
    )

    assert decision.status == ADMISSION_OBSERVE_ONLY
    assert decision.model_decision_run is False
    assert decision.production_admissible is False
    assert decision.automatic_wagering is False


def test_repeatable_admission_blocks_stale_or_unaligned_inputs():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=600,
        ),
    )
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=calibrated_policy(max_cross_modal_skew_ms=500),
    )

    assert decision.status == ADMISSION_BLOCKED
    assert decision.retroactive_promotion_allowed is False


def test_repeatable_admission_only_reaches_human_review_not_model_execution():
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=100,
        ),
    )
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=calibrated_policy(),
    )

    assert decision.status == ADMISSION_ELIGIBLE_REVIEW
    assert decision.model_decision_run is False
    assert decision.production_admissible is False
    assert decision.automatic_provider_switch is False
    assert decision.automatic_model_promotion is False
    assert decision.automatic_wagering is False
