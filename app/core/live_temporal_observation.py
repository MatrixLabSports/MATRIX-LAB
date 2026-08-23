from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Any

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _text(value: object, *, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name.upper()}_REQUIRED")
    return text


def _milliseconds(later: datetime, earlier: datetime) -> int:
    value = int(round((later - earlier).total_seconds() * 1000))
    if value < 0:
        raise ValueError("NEGATIVE_LIVE_STAGE_DURATION")
    return value


def _canonical(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LiveStageLatency:
    source_age_at_ingestion_ms: int
    request_to_response_ms: int
    response_to_ingestion_ms: int
    ingestion_to_normalization_ms: int
    normalization_to_feature_ms: int
    feature_to_inference_ms: int | None
    inference_to_signal_ms: int | None
    observed_to_ready_ms: int
    observed_to_signal_ms: int | None

    def payload(self) -> dict[str, int | None]:
        return asdict(self)


@dataclass(frozen=True)
class LiveTemporalObservation:
    sport: str
    provider_key: str
    subject_key: str
    modality: str
    correlation_id: str
    sequence_id: int
    observed_at: datetime
    request_started_at: datetime
    response_received_at: datetime
    ingested_at: datetime
    normalized_at: datetime
    feature_ready_at: datetime
    inference_completed_at: datetime | None
    signal_emitted_at: datetime | None
    source_record_fingerprint: str | None
    observation_fingerprint: str

    def latency(self) -> LiveStageLatency:
        inference_ms = (
            None
            if self.inference_completed_at is None
            else _milliseconds(
                self.inference_completed_at,
                self.feature_ready_at,
            )
        )
        signal_ms = (
            None
            if self.signal_emitted_at is None
            or self.inference_completed_at is None
            else _milliseconds(
                self.signal_emitted_at,
                self.inference_completed_at,
            )
        )
        return LiveStageLatency(
            source_age_at_ingestion_ms=_milliseconds(
                self.ingested_at,
                self.observed_at,
            ),
            request_to_response_ms=_milliseconds(
                self.response_received_at,
                self.request_started_at,
            ),
            response_to_ingestion_ms=_milliseconds(
                self.ingested_at,
                self.response_received_at,
            ),
            ingestion_to_normalization_ms=_milliseconds(
                self.normalized_at,
                self.ingested_at,
            ),
            normalization_to_feature_ms=_milliseconds(
                self.feature_ready_at,
                self.normalized_at,
            ),
            feature_to_inference_ms=inference_ms,
            inference_to_signal_ms=signal_ms,
            observed_to_ready_ms=_milliseconds(
                self.feature_ready_at,
                self.observed_at,
            ),
            observed_to_signal_ms=(
                None
                if self.signal_emitted_at is None
                else _milliseconds(
                    self.signal_emitted_at,
                    self.observed_at,
                )
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "matrix.live-temporal-observation/2",
            "sport": self.sport,
            "provider_key": self.provider_key,
            "subject_key": self.subject_key,
            "modality": self.modality,
            "correlation_id": self.correlation_id,
            "sequence_id": self.sequence_id,
            "observed_at": self.observed_at.isoformat(),
            "request_started_at": self.request_started_at.isoformat(),
            "response_received_at": self.response_received_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "normalized_at": self.normalized_at.isoformat(),
            "feature_ready_at": self.feature_ready_at.isoformat(),
            "inference_completed_at": (
                None
                if self.inference_completed_at is None
                else self.inference_completed_at.isoformat()
            ),
            "signal_emitted_at": (
                None
                if self.signal_emitted_at is None
                else self.signal_emitted_at.isoformat()
            ),
            "source_record_fingerprint": self.source_record_fingerprint,
            "observation_fingerprint": self.observation_fingerprint,
            "latency": self.latency().payload(),
            "point_in_time_enforced": True,
            "missing_is_zero": False,
            "automatic_provider_switch": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }


def build_live_temporal_observation(
    *,
    sport: str,
    provider_key: str,
    subject_key: str,
    modality: str,
    correlation_id: str,
    sequence_id: int,
    observed_at: datetime,
    request_started_at: datetime,
    response_received_at: datetime,
    ingested_at: datetime,
    normalized_at: datetime,
    feature_ready_at: datetime,
    inference_completed_at: datetime | None = None,
    signal_emitted_at: datetime | None = None,
    source_record_fingerprint: str | None = None,
) -> LiveTemporalObservation:
    sport_value = _text(sport, name="sport").lower()
    provider_value = _text(provider_key, name="provider_key").lower()
    subject_value = _text(subject_key, name="subject_key")
    modality_value = _text(modality, name="modality").lower()
    correlation_value = _text(correlation_id, name="correlation_id").lower()

    if _HEX64.fullmatch(correlation_value) is None:
        raise ValueError("CORRELATION_ID_MUST_BE_SHA256")
    if not isinstance(sequence_id, int) or isinstance(sequence_id, bool):
        raise ValueError("SEQUENCE_ID_MUST_BE_INTEGER")
    if sequence_id < 1:
        raise ValueError("SEQUENCE_ID_MUST_BE_POSITIVE")

    source_fp = None
    if source_record_fingerprint is not None:
        source_fp = _text(
            source_record_fingerprint,
            name="source_record_fingerprint",
        ).lower()
        if _HEX64.fullmatch(source_fp) is None:
            raise ValueError("SOURCE_RECORD_FINGERPRINT_MUST_BE_SHA256")

    times = {
        "observed_at": _utc(observed_at, name="observed_at"),
        "request_started_at": _utc(
            request_started_at,
            name="request_started_at",
        ),
        "response_received_at": _utc(
            response_received_at,
            name="response_received_at",
        ),
        "ingested_at": _utc(ingested_at, name="ingested_at"),
        "normalized_at": _utc(normalized_at, name="normalized_at"),
        "feature_ready_at": _utc(
            feature_ready_at,
            name="feature_ready_at",
        ),
        "inference_completed_at": (
            None
            if inference_completed_at is None
            else _utc(
                inference_completed_at,
                name="inference_completed_at",
            )
        ),
        "signal_emitted_at": (
            None
            if signal_emitted_at is None
            else _utc(signal_emitted_at, name="signal_emitted_at")
        ),
    }

    if times["observed_at"] > times["ingested_at"]:
        raise ValueError("OBSERVED_AT_AFTER_INGESTION")

    ordered = (
        ("request_started_at", "response_received_at"),
        ("response_received_at", "ingested_at"),
        ("ingested_at", "normalized_at"),
        ("normalized_at", "feature_ready_at"),
    )
    for left, right in ordered:
        if times[left] > times[right]:
            raise ValueError(
                f"LIVE_STAGE_TIME_ORDER_INVALID:{left}>{right}"
            )

    inference = times["inference_completed_at"]
    signal = times["signal_emitted_at"]

    if inference is not None and times["feature_ready_at"] > inference:
        raise ValueError(
            "LIVE_STAGE_TIME_ORDER_INVALID:"
            "feature_ready_at>inference_completed_at"
        )
    if signal is not None and inference is None:
        raise ValueError("SIGNAL_REQUIRES_INFERENCE_TIMESTAMP")
    if signal is not None and inference is not None and inference > signal:
        raise ValueError(
            "LIVE_STAGE_TIME_ORDER_INVALID:"
            "inference_completed_at>signal_emitted_at"
        )

    base = {
        "schema": "matrix.live-temporal-observation/2",
        "sport": sport_value,
        "provider_key": provider_value,
        "subject_key": subject_value,
        "modality": modality_value,
        "correlation_id": correlation_value,
        "sequence_id": sequence_id,
        "observed_at": times["observed_at"].isoformat(),
        "request_started_at": times["request_started_at"].isoformat(),
        "response_received_at": times["response_received_at"].isoformat(),
        "ingested_at": times["ingested_at"].isoformat(),
        "normalized_at": times["normalized_at"].isoformat(),
        "feature_ready_at": times["feature_ready_at"].isoformat(),
        "inference_completed_at": (
            None if inference is None else inference.isoformat()
        ),
        "signal_emitted_at": (
            None if signal is None else signal.isoformat()
        ),
        "source_record_fingerprint": source_fp,
        "point_in_time_enforced": True,
        "missing_is_zero": False,
        "automatic_provider_switch": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return LiveTemporalObservation(
        sport=sport_value,
        provider_key=provider_value,
        subject_key=subject_value,
        modality=modality_value,
        correlation_id=correlation_value,
        sequence_id=sequence_id,
        observed_at=times["observed_at"],
        request_started_at=times["request_started_at"],
        response_received_at=times["response_received_at"],
        ingested_at=times["ingested_at"],
        normalized_at=times["normalized_at"],
        feature_ready_at=times["feature_ready_at"],
        inference_completed_at=inference,
        signal_emitted_at=signal,
        source_record_fingerprint=source_fp,
        observation_fingerprint=_sha(base),
    )
