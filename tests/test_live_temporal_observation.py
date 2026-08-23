from datetime import UTC, datetime, timedelta

import pytest

from app.core.live_temporal_observation import (
    build_live_temporal_observation,
)


BASE = datetime(2026, 8, 23, 16, tzinfo=UTC)


def make_observation(**overrides):
    values = dict(
        sport="football",
        subject_key="fixture:1557375",
        modality="fixture_events",
        correlation_id="a" * 64,
        sequence_id=1,
        observed_at=BASE,
        request_started_at=BASE + timedelta(milliseconds=100),
        response_received_at=BASE + timedelta(milliseconds=200),
        ingested_at=BASE + timedelta(milliseconds=250),
        normalized_at=BASE + timedelta(milliseconds=300),
        feature_ready_at=BASE + timedelta(milliseconds=350),
        inference_completed_at=None,
        signal_emitted_at=None,
        source_record_fingerprint="b" * 64,
    )
    values.update(overrides)
    return build_live_temporal_observation(**values)


def test_temporal_observation_records_explicit_ingestion_normalization_and_latency():
    observation = make_observation()
    latency = observation.latency()

    assert observation.ingested_at == BASE + timedelta(milliseconds=250)
    assert observation.normalized_at == BASE + timedelta(milliseconds=300)
    assert latency.source_age_at_ingestion_ms == 250
    assert latency.request_to_response_ms == 100
    assert latency.response_to_ingestion_ms == 50
    assert latency.ingestion_to_normalization_ms == 50
    assert latency.normalization_to_feature_ms == 50
    assert latency.observed_to_ready_ms == 350


def test_temporal_observation_requires_aware_timestamps():
    with pytest.raises(ValueError, match="OBSERVED_AT_MUST_BE_TIMEZONE_AWARE"):
        make_observation(observed_at=datetime(2026, 8, 23, 16))


def test_temporal_observation_fails_closed_on_negative_stage_duration():
    with pytest.raises(ValueError, match="LIVE_STAGE_TIME_ORDER_INVALID"):
        make_observation(
            normalized_at=BASE + timedelta(milliseconds=240),
        )


def test_signal_requires_inference_and_order():
    with pytest.raises(ValueError, match="SIGNAL_REQUIRES_INFERENCE_TIMESTAMP"):
        make_observation(
            signal_emitted_at=BASE + timedelta(milliseconds=500),
        )


def test_observation_fingerprint_is_deterministic_and_missing_is_not_zero():
    first = make_observation()
    second = make_observation()

    assert first.observation_fingerprint == second.observation_fingerprint
    payload = first.payload()
    assert payload["missing_is_zero"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_wagering"] is False
