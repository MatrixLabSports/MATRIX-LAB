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
EVALUATED_AT = BASE + timedelta(seconds=2)


def observation(
    *,
    modality="fixture_events",
    sequence_id=1,
    observed_offset_ms=0,
    correlation_id="a" * 64,
    subject_key="fixture:1557375",
    provider_key="api_football",
    source_record_fingerprint=None,
):
    observed = BASE + timedelta(milliseconds=observed_offset_ms)
    return build_live_temporal_observation(
        sport="football",
        provider_key=provider_key,
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
            source_record_fingerprint
            if source_record_fingerprint is not None
            else f"{sequence_id:064x}"[-64:]
        ),
    )


def calibrated_policy(**overrides):
    values = dict(
        fixture_status_max_source_age_ms=500,
        fixture_statistics_max_source_age_ms=500,
        fixture_events_max_source_age_ms=500,
        odds_max_source_age_ms=500,
        fixture_status_max_decision_age_ms=5000,
        fixture_statistics_max_decision_age_ms=5000,
        fixture_events_max_decision_age_ms=5000,
        odds_max_decision_age_ms=5000,
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
        evaluated_at=EVALUATED_AT,
    )

    assert policy.thresholds_empirically_calibrated is False
    assert policy.production_admissible is False
    assert decision.status == FRESHNESS_OBSERVE_ONLY
    assert "SOURCE_AGE_THRESHOLD_UNCALIBRATED" in decision.reason_codes


def test_explicit_policy_can_pass_without_becoming_production_policy():
    decision = evaluate_football_live_freshness(
        observation(),
        calibrated_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == FRESHNESS_PASS
    assert decision.production_admissible is False
    assert decision.model_decision_run is False


def test_stale_input_fails_closed():
    item = observation()
    policy = calibrated_policy(
        fixture_events_max_source_age_ms=50,
    )
    decision = evaluate_football_live_freshness(
        item,
        policy,
        evaluated_at=EVALUATED_AT,
    )

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
        provider_key=first.provider_key,
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


def test_repeatable_admission_is_observe_only_until_policy_is_explicit(tmp_path):
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=100,
        ),
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    for item in items:
        store.record(item)
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=FootballLiveFreshnessPolicy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_OBSERVE_ONLY
    assert decision.model_decision_run is False
    assert decision.production_admissible is False
    assert decision.automatic_wagering is False


def test_repeatable_admission_blocks_stale_or_unaligned_inputs(tmp_path):
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=600,
        ),
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    for item in items:
        store.record(item)
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=calibrated_policy(max_cross_modal_skew_ms=500),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert decision.retroactive_promotion_allowed is False


def test_repeatable_admission_only_reaches_human_review_not_model_execution(tmp_path):
    items = (
        observation(modality="fixture_statistics"),
        observation(
            modality="fixture_events",
            observed_offset_ms=100,
        ),
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    for item in items:
        store.record(item)
    decision = evaluate_repeatable_football_live_admission(
        items,
        policy=calibrated_policy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_ELIGIBLE_REVIEW
    assert decision.model_decision_run is False
    assert decision.production_admissible is False
    assert decision.automatic_provider_switch is False
    assert decision.automatic_model_promotion is False
    assert decision.automatic_wagering is False


def test_newer_sequence_with_older_observed_at_is_quarantined_as_late(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    first = observation(sequence_id=1, observed_offset_ms=100)
    late = observation(sequence_id=2, observed_offset_ms=0)

    assert store.record(first).status == "ACCEPTED"
    decision = store.record(late)

    assert decision.status == "QUARANTINED_LATE_OBSERVATION"
    assert "OBSERVED_AT_REGRESSION" in decision.reason_codes
    assert decision.accepted_for_fusion is False
    assert store.audit_integrity() is True


def test_same_source_record_across_new_sequence_is_idempotent_no_double_count(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(sequence_id=1)

    duplicate = build_live_temporal_observation(
        sport="football",
        provider_key=first.provider_key,
        subject_key=first.subject_key,
        modality=first.modality,
        correlation_id=first.correlation_id,
        sequence_id=2,
        observed_at=first.observed_at + timedelta(milliseconds=50),
        request_started_at=first.request_started_at + timedelta(milliseconds=50),
        response_received_at=first.response_received_at + timedelta(milliseconds=50),
        ingested_at=first.ingested_at + timedelta(milliseconds=50),
        normalized_at=first.normalized_at + timedelta(milliseconds=50),
        feature_ready_at=first.feature_ready_at + timedelta(milliseconds=50),
        source_record_fingerprint=first.source_record_fingerprint,
    )

    first_decision = store.record(first)
    duplicate_decision = store.record(duplicate)

    assert first_decision.status == "ACCEPTED"
    assert duplicate_decision.status == "IDEMPOTENT_DUPLICATE_SOURCE"
    assert duplicate_decision.idempotent is True
    assert duplicate_decision.accepted_for_fusion is False

    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM football_live_observation"
        ).fetchone()[0]
    assert count == 1
    assert store.audit_integrity() is True


def test_integrity_detects_status_tampering(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    item = observation()
    store.record(item)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET status = 'QUARANTINED_OUT_OF_ORDER'
            WHERE observation_fingerprint = ?
            """,
            (item.observation_fingerprint,),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_integrity_detects_reason_code_tampering(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    item = observation()
    store.record(item)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET reason_codes_json = ?
            WHERE observation_fingerprint = ?
            """,
            ('["FAKE_REASON"]\n', item.observation_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_integrity_detects_sequence_column_tampering(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    item = observation(sequence_id=1)
    store.record(item)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET sequence_id = 99
            WHERE observation_fingerprint = ?
            """,
            (item.observation_fingerprint,),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_concurrent_duplicate_source_does_not_double_count(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(sequence_id=1)

    items = []
    for sequence_id in range(1, 9):
        items.append(
            build_live_temporal_observation(
                sport="football",
                provider_key=first.provider_key,
                subject_key=first.subject_key,
                modality=first.modality,
                correlation_id=first.correlation_id,
                sequence_id=sequence_id,
                observed_at=first.observed_at + timedelta(milliseconds=sequence_id),
                request_started_at=first.request_started_at + timedelta(milliseconds=sequence_id),
                response_received_at=first.response_received_at + timedelta(milliseconds=sequence_id),
                ingested_at=first.ingested_at + timedelta(milliseconds=sequence_id),
                normalized_at=first.normalized_at + timedelta(milliseconds=sequence_id),
                feature_ready_at=first.feature_ready_at + timedelta(milliseconds=sequence_id),
                source_record_fingerprint=first.source_record_fingerprint,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(store.record, items))

    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM football_live_observation"
        ).fetchone()[0]

    assert count == 1
    assert sum(d.status == "ACCEPTED" for d in decisions) == 1
    assert sum(
        d.status == "IDEMPOTENT_DUPLICATE_SOURCE"
        for d in decisions
    ) == 7
    assert store.audit_integrity() is True


def test_cross_modal_alignment_requires_distinct_modalities():
    items = (
        observation(
            modality="fixture_events",
            sequence_id=1,
            source_record_fingerprint="1" * 64,
        ),
        observation(
            modality="fixture_events",
            sequence_id=2,
            observed_offset_ms=100,
            source_record_fingerprint="2" * 64,
        ),
    )
    decision = evaluate_football_cross_modal_alignment(
        items,
        calibrated_policy(),
    )
    assert decision.status == ALIGNMENT_BLOCKED
    assert "DISTINCT_MODALITIES_REQUIRED" in decision.reason_codes


def test_cross_modal_alignment_requires_same_provider():
    items = (
        observation(
            modality="fixture_statistics",
            provider_key="api_football",
            source_record_fingerprint="3" * 64,
        ),
        observation(
            modality="fixture_events",
            provider_key="other_provider",
            observed_offset_ms=100,
            source_record_fingerprint="4" * 64,
        ),
    )
    decision = evaluate_football_cross_modal_alignment(
        items,
        calibrated_policy(),
    )
    assert decision.status == ALIGNMENT_BLOCKED
    assert "PROVIDER_KEY_MISMATCH" in decision.reason_codes


def test_repeatable_store_requires_source_record_fingerprint(tmp_path):
    item = build_live_temporal_observation(
        sport="football",
        provider_key="api_football",
        subject_key="fixture:1557375",
        modality="fixture_events",
        correlation_id="a" * 64,
        sequence_id=1,
        observed_at=BASE,
        request_started_at=BASE + timedelta(milliseconds=20),
        response_received_at=BASE + timedelta(milliseconds=40),
        ingested_at=BASE + timedelta(milliseconds=60),
        normalized_at=BASE + timedelta(milliseconds=80),
        feature_ready_at=BASE + timedelta(milliseconds=100),
        source_record_fingerprint=None,
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    with pytest.raises(
        ValueError,
        match="SOURCE_RECORD_FINGERPRINT_REQUIRED_FOR_REPEATABLE_LIVE",
    ):
        store.record(item)


def test_idempotent_replay_revalidates_persisted_status_and_reasons(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    item = observation(source_record_fingerprint="5" * 64)
    store.record(item)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET status = ?, reason_codes_json = ?
            WHERE observation_fingerprint = ?
            """,
            ("ACCEPTED", '["FORGED"]', item.observation_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match="LIVE_EVIDENCE_REASON_REDERIVATION_FAILED",
    ):
        store.record(item)


def test_repeatable_admission_requires_durable_accepted_sequence_evidence(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    stats = observation(
        modality="fixture_statistics",
        source_record_fingerprint="6" * 64,
    )
    event = observation(
        modality="fixture_events",
        observed_offset_ms=100,
        source_record_fingerprint="7" * 64,
    )
    store.record(stats)

    decision = evaluate_repeatable_football_live_admission(
        (stats, event),
        policy=calibrated_policy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert "DURABLE_SEQUENCE_EVIDENCE_MISSING" in decision.reason_codes


def test_repeatable_admission_blocks_quarantined_late_observation(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    stats = observation(
        modality="fixture_statistics",
        sequence_id=1,
        observed_offset_ms=100,
        source_record_fingerprint="8" * 64,
    )
    event_recent = observation(
        modality="fixture_events",
        sequence_id=1,
        observed_offset_ms=500,
        source_record_fingerprint="9" * 64,
    )
    event_late = observation(
        modality="fixture_events",
        sequence_id=2,
        observed_offset_ms=100,
        source_record_fingerprint="a" * 64,
    )

    store.record(stats)
    store.record(event_recent)
    late_decision = store.record(event_late)
    assert late_decision.accepted_for_fusion is False

    decision = evaluate_repeatable_football_live_admission(
        (stats, event_late),
        policy=calibrated_policy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert "OBSERVED_AT_REGRESSION" in decision.reason_codes


def test_repeatable_admission_blocks_tampered_durable_evidence(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    stats = observation(
        modality="fixture_statistics",
        source_record_fingerprint="b" * 64,
    )
    event = observation(
        modality="fixture_events",
        observed_offset_ms=100,
        source_record_fingerprint="c" * 64,
    )
    store.record(stats)
    store.record(event)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET reason_codes_json = ?
            WHERE observation_fingerprint = ?
            """,
            ('["FORGED"]', event.observation_fingerprint),
        )
        connection.commit()

    decision = evaluate_repeatable_football_live_admission(
        (stats, event),
        policy=calibrated_policy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert "DURABLE_SEQUENCE_EVIDENCE_INVALID" in decision.reason_codes


def test_decision_time_staleness_blocks_even_when_ingestion_was_fresh(tmp_path):
    ancient = datetime(2020, 1, 1, tzinfo=UTC)

    def ancient_observation(*, modality, source_char):
        return build_live_temporal_observation(
            sport="football",
            provider_key="api_football",
            subject_key="fixture:1557375",
            modality=modality,
            correlation_id="d" * 64,
            sequence_id=1,
            observed_at=ancient,
            request_started_at=ancient + timedelta(milliseconds=1),
            response_received_at=ancient + timedelta(milliseconds=2),
            ingested_at=ancient + timedelta(milliseconds=3),
            normalized_at=ancient + timedelta(milliseconds=4),
            feature_ready_at=ancient + timedelta(milliseconds=5),
            source_record_fingerprint=source_char * 64,
        )

    stats = ancient_observation(
        modality="fixture_statistics",
        source_char="d",
    )
    events = ancient_observation(
        modality="fixture_events",
        source_char="e",
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    store.record(stats)
    store.record(events)

    decision = evaluate_repeatable_football_live_admission(
        (stats, events),
        policy=calibrated_policy(
            fixture_statistics_max_decision_age_ms=500,
            fixture_events_max_decision_age_ms=500,
        ),
        evidence_store=store,
        evaluated_at=BASE,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert "DECISION_AGE_EXCEEDED" in decision.reason_codes


def test_uncalibrated_decision_time_threshold_never_becomes_eligible(tmp_path):
    stats = observation(
        modality="fixture_statistics",
        source_record_fingerprint="1" * 64,
    )
    events = observation(
        modality="fixture_events",
        observed_offset_ms=100,
        source_record_fingerprint="2" * 64,
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    store.record(stats)
    store.record(events)

    policy = calibrated_policy(
        fixture_statistics_max_decision_age_ms=None,
    )
    decision = evaluate_repeatable_football_live_admission(
        (stats, events),
        policy=policy,
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_OBSERVE_ONLY
    assert "DECISION_AGE_THRESHOLD_UNCALIBRATED" in decision.reason_codes


def test_duplicate_modality_bundle_is_blocked_even_with_two_distinct_modalities(tmp_path):
    stats_1 = observation(
        modality="fixture_statistics",
        sequence_id=1,
        source_record_fingerprint="3" * 64,
    )
    stats_2 = observation(
        modality="fixture_statistics",
        sequence_id=2,
        observed_offset_ms=10,
        source_record_fingerprint="4" * 64,
    )
    events = observation(
        modality="fixture_events",
        sequence_id=1,
        observed_offset_ms=20,
        source_record_fingerprint="5" * 64,
    )
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    for item in (stats_1, stats_2, events):
        store.record(item)

    decision = evaluate_repeatable_football_live_admission(
        (stats_1, stats_2, events),
        policy=calibrated_policy(),
        evidence_store=store,
        evaluated_at=EVALUATED_AT,
    )

    assert decision.status == ADMISSION_BLOCKED
    assert "DUPLICATE_MODALITY_IN_BUNDLE" in decision.reason_codes


def test_correlation_id_cannot_reset_global_stream_order(tmp_path):
    store = SQLiteFootballLiveObservationStore(tmp_path / "live.sqlite3")
    newer = observation(
        modality="fixture_events",
        sequence_id=2,
        observed_offset_ms=200,
        correlation_id="a" * 64,
        source_record_fingerprint="6" * 64,
    )
    older_new_cycle = observation(
        modality="fixture_events",
        sequence_id=1,
        observed_offset_ms=100,
        correlation_id="b" * 64,
        source_record_fingerprint="7" * 64,
    )

    assert store.record(newer).status == "ACCEPTED"
    decision = store.record(older_new_cycle)

    assert decision.status == "QUARANTINED_OUT_OF_ORDER"
    assert decision.accepted_for_fusion is False
    assert store.audit_integrity() is True


def test_record_fails_closed_when_prior_stream_history_is_corrupted(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=3,
        observed_offset_ms=300,
        source_record_fingerprint="8" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_observation
            SET sequence_id = 1
            WHERE observation_fingerprint = ?
            """,
            (first.observation_fingerprint,),
        )
        connection.commit()

    candidate = observation(
        modality="fixture_events",
        sequence_id=2,
        observed_offset_ms=200,
        source_record_fingerprint="9" * 64,
    )

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match=(
            "LIVE_EVIDENCE_SEQUENCE_COLUMN_MISMATCH"
            "|LIVE_LEDGER_ANCHOR_DERIVATION_MISMATCH"
            "|LIVE_STREAM_STATE_DERIVATION_MISMATCH"
        ),
    ):
        store.record(candidate)


def test_deleted_history_is_detected_by_durable_ledger_anchor(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=3,
        observed_offset_ms=300,
        source_record_fingerprint="a" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM football_live_observation")
        connection.commit()

    assert store.audit_integrity() is False

    candidate = observation(
        modality="fixture_events",
        sequence_id=2,
        observed_offset_ms=200,
        source_record_fingerprint="b" * 64,
    )
    with pytest.raises(
        ValueError,
        match=(
            "LIVE_STREAM_STATE_MEMBERSHIP_MISMATCH"
            "|LIVE_LEDGER_ANCHOR_DERIVATION_MISMATCH"
        ),
    ):
        store.record(candidate)


def test_deleting_stream_state_is_detected_before_next_write(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=1,
        source_record_fingerprint="c" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM football_live_stream_state")
        connection.commit()

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match="LIVE_STREAM_STATE_MEMBERSHIP_MISMATCH",
    ):
        store.record(
            observation(
                modality="fixture_events",
                sequence_id=2,
                observed_offset_ms=100,
                source_record_fingerprint="d" * 64,
            )
        )


def test_deleting_global_anchor_is_detected_before_next_write(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=1,
        source_record_fingerprint="e" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM football_live_ledger_anchor")
        connection.commit()

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match="LIVE_LEDGER_ANCHOR_MISSING",
    ):
        store.record(
            observation(
                modality="fixture_events",
                sequence_id=2,
                observed_offset_ms=100,
                source_record_fingerprint="f" * 64,
            )
        )


def test_decision_time_must_be_timezone_aware():
    item = observation()
    with pytest.raises(
        ValueError,
        match="EVALUATED_AT_MUST_BE_TIMEZONE_AWARE",
    ):
        evaluate_football_live_freshness(
            item,
            calibrated_policy(),
            evaluated_at=datetime(2026, 8, 23, 16),
        )


def test_decision_time_cannot_precede_feature_ready():
    item = observation()
    with pytest.raises(
        ValueError,
        match="DECISION_TIME_BEFORE_FEATURE_READY",
    ):
        evaluate_football_live_freshness(
            item,
            calibrated_policy(),
            evaluated_at=item.normalized_at,
        )


def test_deleting_rows_and_stream_state_is_still_detected_by_global_anchor(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=1,
        source_record_fingerprint="0" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM football_live_observation")
        connection.execute("DELETE FROM football_live_stream_state")
        connection.commit()

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match="LIVE_LEDGER_ANCHOR_DERIVATION_MISMATCH",
    ):
        store.record(
            observation(
                modality="fixture_events",
                sequence_id=2,
                observed_offset_ms=100,
                source_record_fingerprint="1" * 64,
            )
        )


def test_tampered_stream_state_hash_is_detected(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveObservationStore(path)
    first = observation(
        modality="fixture_events",
        sequence_id=1,
        source_record_fingerprint="2" * 64,
    )
    store.record(first)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_stream_state
            SET record_count = record_count + 1
            """
        )
        connection.commit()

    assert store.audit_integrity() is False
    with pytest.raises(
        ValueError,
        match="LIVE_STREAM_STATE_HASH_MISMATCH",
    ):
        store.verify_for_fusion(first)
