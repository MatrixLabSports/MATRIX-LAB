from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from app.core.live_temporal_observation import (
    LiveTemporalObservation,
)

FOOTBALL_LIVE_MODALITIES = (
    "fixture_status",
    "fixture_statistics",
    "fixture_events",
    "odds",
)

FRESHNESS_PASS = "PASS"
FRESHNESS_OBSERVE_ONLY = "OBSERVE_ONLY_UNCALIBRATED"
FRESHNESS_BLOCKED = "BLOCKED_STALE"

ALIGNMENT_PASS = "PASS"
ALIGNMENT_OBSERVE_ONLY = "OBSERVE_ONLY_UNCALIBRATED"
ALIGNMENT_BLOCKED = "BLOCKED_UNALIGNED"

ADMISSION_BLOCKED = "BLOCKED"
ADMISSION_OBSERVE_ONLY = "OBSERVE_ONLY"
ADMISSION_ELIGIBLE_REVIEW = "ELIGIBLE_FOR_MODEL_REVIEW"


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


def _expected_observation_fingerprint(
    payload: Mapping[str, Any],
) -> str:
    base = {
        "schema": "matrix.live-temporal-observation/1",
        "sport": payload.get("sport"),
        "subject_key": payload.get("subject_key"),
        "modality": payload.get("modality"),
        "correlation_id": payload.get("correlation_id"),
        "sequence_id": payload.get("sequence_id"),
        "observed_at": payload.get("observed_at"),
        "request_started_at": payload.get("request_started_at"),
        "response_received_at": payload.get("response_received_at"),
        "ingested_at": payload.get("ingested_at"),
        "normalized_at": payload.get("normalized_at"),
        "feature_ready_at": payload.get("feature_ready_at"),
        "inference_completed_at": payload.get("inference_completed_at"),
        "signal_emitted_at": payload.get("signal_emitted_at"),
        "source_record_fingerprint": payload.get(
            "source_record_fingerprint"
        ),
        "point_in_time_enforced": True,
        "missing_is_zero": False,
        "automatic_provider_switch": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }
    return _sha(base)


def _positive_or_none(
    value: int | None,
    *,
    name: str,
) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name.upper()}_MUST_BE_POSITIVE_INTEGER_OR_NONE")
    return value


@dataclass(frozen=True)
class FootballLiveFreshnessPolicy:
    fixture_status_max_source_age_ms: int | None = None
    fixture_statistics_max_source_age_ms: int | None = None
    fixture_events_max_source_age_ms: int | None = None
    odds_max_source_age_ms: int | None = None
    max_ingestion_to_normalization_ms: int | None = None
    max_normalization_to_feature_ms: int | None = None
    max_cross_modal_skew_ms: int | None = None

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _positive_or_none(value, name=name)

    def source_age_limit(self, modality: str) -> int | None:
        mapping = {
            "fixture_status": self.fixture_status_max_source_age_ms,
            "fixture_statistics": (
                self.fixture_statistics_max_source_age_ms
            ),
            "fixture_events": self.fixture_events_max_source_age_ms,
            "odds": self.odds_max_source_age_ms,
        }
        if modality not in mapping:
            raise ValueError("UNSUPPORTED_FOOTBALL_LIVE_MODALITY")
        return mapping[modality]

    @property
    def thresholds_empirically_calibrated(self) -> bool:
        return False

    @property
    def production_admissible(self) -> bool:
        return False


@dataclass(frozen=True)
class FootballLiveFreshnessDecision:
    modality: str
    status: str
    reason_codes: tuple[str, ...]
    source_age_ms: int
    ingestion_to_normalization_ms: int
    normalization_to_feature_ms: int
    production_admissible: bool = False
    model_decision_run: bool = False


def evaluate_football_live_freshness(
    observation: LiveTemporalObservation,
    policy: FootballLiveFreshnessPolicy,
) -> FootballLiveFreshnessDecision:
    if observation.sport != "football":
        raise ValueError("FOOTBALL_LIVE_SPORT_REQUIRED")
    if observation.modality not in FOOTBALL_LIVE_MODALITIES:
        raise ValueError("UNSUPPORTED_FOOTBALL_LIVE_MODALITY")

    latency = observation.latency()
    reasons: list[str] = []
    uncalibrated = False

    source_limit = policy.source_age_limit(observation.modality)
    if source_limit is None:
        reasons.append("SOURCE_AGE_THRESHOLD_UNCALIBRATED")
        uncalibrated = True
    elif latency.source_age_at_ingestion_ms > source_limit:
        reasons.append("SOURCE_AGE_EXCEEDED")

    ingest_limit = policy.max_ingestion_to_normalization_ms
    if ingest_limit is None:
        reasons.append("INGESTION_NORMALIZATION_THRESHOLD_UNCALIBRATED")
        uncalibrated = True
    elif latency.ingestion_to_normalization_ms > ingest_limit:
        reasons.append("INGESTION_NORMALIZATION_LATENCY_EXCEEDED")

    feature_limit = policy.max_normalization_to_feature_ms
    if feature_limit is None:
        reasons.append("NORMALIZATION_FEATURE_THRESHOLD_UNCALIBRATED")
        uncalibrated = True
    elif latency.normalization_to_feature_ms > feature_limit:
        reasons.append("NORMALIZATION_FEATURE_LATENCY_EXCEEDED")

    stale = any(code.endswith("EXCEEDED") for code in reasons)
    if stale:
        status = FRESHNESS_BLOCKED
    elif uncalibrated:
        status = FRESHNESS_OBSERVE_ONLY
    else:
        status = FRESHNESS_PASS
        reasons.append("FRESHNESS_WITHIN_EXPLICIT_POLICY")

    return FootballLiveFreshnessDecision(
        modality=observation.modality,
        status=status,
        reason_codes=tuple(reasons),
        source_age_ms=latency.source_age_at_ingestion_ms,
        ingestion_to_normalization_ms=(
            latency.ingestion_to_normalization_ms
        ),
        normalization_to_feature_ms=(
            latency.normalization_to_feature_ms
        ),
    )


@dataclass(frozen=True)
class FootballCrossModalAlignment:
    status: str
    reason_codes: tuple[str, ...]
    subject_key: str | None
    correlation_id: str | None
    modalities: tuple[str, ...]
    max_observed_at_skew_ms: int | None
    synchronous_snapshot: bool = False
    production_admissible: bool = False


def evaluate_football_cross_modal_alignment(
    observations: Iterable[LiveTemporalObservation],
    policy: FootballLiveFreshnessPolicy,
) -> FootballCrossModalAlignment:
    items = tuple(observations)
    if len(items) < 2:
        raise ValueError("CROSS_MODAL_ALIGNMENT_REQUIRES_AT_LEAST_TWO")

    reasons: list[str] = []

    if any(item.sport != "football" for item in items):
        return FootballCrossModalAlignment(
            status=ALIGNMENT_BLOCKED,
            reason_codes=("CROSS_SPORT_ALIGNMENT_FORBIDDEN",),
            subject_key=None,
            correlation_id=None,
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=None,
        )

    subjects = {item.subject_key for item in items}
    correlations = {item.correlation_id for item in items}

    if len(subjects) != 1:
        reasons.append("SUBJECT_IDENTITY_MISMATCH")
    if len(correlations) != 1:
        reasons.append("CORRELATION_ID_MISMATCH")

    if reasons:
        return FootballCrossModalAlignment(
            status=ALIGNMENT_BLOCKED,
            reason_codes=tuple(reasons),
            subject_key=None if len(subjects) != 1 else next(iter(subjects)),
            correlation_id=(
                None if len(correlations) != 1 else next(iter(correlations))
            ),
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=None,
        )

    observed = [item.observed_at for item in items]
    skew_ms = int(
        round((max(observed) - min(observed)).total_seconds() * 1000)
    )

    tolerance = policy.max_cross_modal_skew_ms
    if tolerance is None:
        return FootballCrossModalAlignment(
            status=ALIGNMENT_OBSERVE_ONLY,
            reason_codes=("ALIGNMENT_TOLERANCE_UNCALIBRATED",),
            subject_key=next(iter(subjects)),
            correlation_id=next(iter(correlations)),
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=skew_ms,
        )

    if skew_ms > tolerance:
        return FootballCrossModalAlignment(
            status=ALIGNMENT_BLOCKED,
            reason_codes=("CROSS_MODAL_SKEW_EXCEEDED",),
            subject_key=next(iter(subjects)),
            correlation_id=next(iter(correlations)),
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=skew_ms,
        )

    return FootballCrossModalAlignment(
        status=ALIGNMENT_PASS,
        reason_codes=("CROSS_MODAL_ALIGNMENT_WITHIN_EXPLICIT_POLICY",),
        subject_key=next(iter(subjects)),
        correlation_id=next(iter(correlations)),
        modalities=tuple(sorted({item.modality for item in items})),
        max_observed_at_skew_ms=skew_ms,
    )


@dataclass(frozen=True)
class FootballLiveSequenceDecision:
    observation_fingerprint: str
    sequence_id: int
    status: str
    reason_codes: tuple[str, ...]
    idempotent: bool
    accepted_for_fusion: bool


class SQLiteFootballLiveObservationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS football_live_observation (
                    observation_fingerprint TEXT PRIMARY KEY,
                    subject_key TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    sequence_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE(subject_key, modality, correlation_id, sequence_id)
                )
                """
            )

    def record(
        self,
        observation: LiveTemporalObservation,
    ) -> FootballLiveSequenceDecision:
        if observation.sport != "football":
            raise ValueError("FOOTBALL_LIVE_SPORT_REQUIRED")

        payload_json = _canonical(observation.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")

                existing = connection.execute(
                    """
                    SELECT
                        observation_fingerprint,
                        status,
                        reason_codes_json
                    FROM football_live_observation
                    WHERE subject_key = ?
                      AND modality = ?
                      AND correlation_id = ?
                      AND sequence_id = ?
                    """,
                    (
                        observation.subject_key,
                        observation.modality,
                        observation.correlation_id,
                        observation.sequence_id,
                    ),
                ).fetchone()

                if existing is not None:
                    existing_fp, status, reasons_json = existing
                    if existing_fp != observation.observation_fingerprint:
                        raise ValueError("LIVE_SEQUENCE_MUTATION_VIOLATION")
                    connection.execute("COMMIT")
                    return FootballLiveSequenceDecision(
                        observation_fingerprint=existing_fp,
                        sequence_id=observation.sequence_id,
                        status=status,
                        reason_codes=tuple(json.loads(reasons_json)),
                        idempotent=True,
                        accepted_for_fusion=status == "ACCEPTED",
                    )

                row = connection.execute(
                    """
                    SELECT MAX(sequence_id)
                    FROM football_live_observation
                    WHERE subject_key = ?
                      AND modality = ?
                      AND correlation_id = ?
                    """,
                    (
                        observation.subject_key,
                        observation.modality,
                        observation.correlation_id,
                    ),
                ).fetchone()

                maximum = None if row is None else row[0]
                if (
                    maximum is not None
                    and observation.sequence_id < int(maximum)
                ):
                    status = "QUARANTINED_OUT_OF_ORDER"
                    reasons = ("OUT_OF_ORDER_SEQUENCE",)
                    accepted = False
                else:
                    status = "ACCEPTED"
                    reasons = ("SEQUENCE_MONOTONIC",)
                    accepted = True

                connection.execute(
                    """
                    INSERT INTO football_live_observation (
                        observation_fingerprint,
                        subject_key,
                        modality,
                        correlation_id,
                        sequence_id,
                        status,
                        reason_codes_json,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_fingerprint,
                        observation.subject_key,
                        observation.modality,
                        observation.correlation_id,
                        observation.sequence_id,
                        status,
                        _canonical(list(reasons)),
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return FootballLiveSequenceDecision(
            observation_fingerprint=observation.observation_fingerprint,
            sequence_id=observation.sequence_id,
            status=status,
            reason_codes=reasons,
            idempotent=False,
            accepted_for_fusion=accepted,
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observation_fingerprint,
                    payload_json,
                    payload_sha256,
                    status,
                    reason_codes_json
                FROM football_live_observation
                ORDER BY created_at, observation_fingerprint
                """
            ).fetchall()

        for observation_fp, payload_json, stored_sha, status, reasons in rows:
            if sha256(payload_json.encode("utf-8")).hexdigest() != stored_sha:
                return False
            try:
                payload = json.loads(payload_json)
                reason_values = json.loads(reasons)
            except json.JSONDecodeError:
                return False
            if payload.get("observation_fingerprint") != observation_fp:
                return False
            if _expected_observation_fingerprint(payload) != observation_fp:
                return False
            if payload.get("sport") != "football":
                return False
            if status not in {"ACCEPTED", "QUARANTINED_OUT_OF_ORDER"}:
                return False
            if not isinstance(reason_values, list) or not reason_values:
                return False
        return True


@dataclass(frozen=True)
class FootballRepeatableLiveAdmission:
    status: str
    reason_codes: tuple[str, ...]
    freshness: tuple[FootballLiveFreshnessDecision, ...]
    alignment: FootballCrossModalAlignment
    model_decision_run: bool = False
    production_admissible: bool = False
    retroactive_promotion_allowed: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False


def evaluate_repeatable_football_live_admission(
    observations: Iterable[LiveTemporalObservation],
    *,
    policy: FootballLiveFreshnessPolicy,
) -> FootballRepeatableLiveAdmission:
    items = tuple(observations)
    if len(items) < 2:
        raise ValueError("REPEATABLE_LIVE_ADMISSION_REQUIRES_MULTIMODAL_INPUT")

    freshness = tuple(
        evaluate_football_live_freshness(item, policy)
        for item in items
    )
    alignment = evaluate_football_cross_modal_alignment(items, policy)

    reasons: list[str] = []
    for decision in freshness:
        reasons.extend(decision.reason_codes)
    reasons.extend(alignment.reason_codes)

    if (
        any(item.status == FRESHNESS_BLOCKED for item in freshness)
        or alignment.status == ALIGNMENT_BLOCKED
    ):
        status = ADMISSION_BLOCKED
    elif (
        any(item.status == FRESHNESS_OBSERVE_ONLY for item in freshness)
        or alignment.status == ALIGNMENT_OBSERVE_ONLY
    ):
        status = ADMISSION_OBSERVE_ONLY
    else:
        status = ADMISSION_ELIGIBLE_REVIEW
        reasons.append("ELIGIBLE_FOR_HUMAN_MODEL_REVIEW_ONLY")

    return FootballRepeatableLiveAdmission(
        status=status,
        reason_codes=tuple(dict.fromkeys(reasons)),
        freshness=freshness,
        alignment=alignment,
    )
