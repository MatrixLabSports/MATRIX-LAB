from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
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

SEQUENCE_ACCEPTED = "ACCEPTED"
SEQUENCE_OUT_OF_ORDER = "QUARANTINED_OUT_OF_ORDER"
SEQUENCE_LATE_OBSERVATION = "QUARANTINED_LATE_OBSERVATION"
SEQUENCE_DUPLICATE_SOURCE = "IDEMPOTENT_DUPLICATE_SOURCE"

REASON_SEQUENCE_MONOTONIC = "SEQUENCE_MONOTONIC"
REASON_OUT_OF_ORDER = "OUT_OF_ORDER_SEQUENCE"
REASON_OBSERVED_AT_REGRESSION = "OBSERVED_AT_REGRESSION"
REASON_SOURCE_ALREADY_SEEN = "SOURCE_RECORD_ALREADY_SEEN"


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
        "schema": "matrix.live-temporal-observation/2",
        "sport": payload.get("sport"),
        "provider_key": payload.get("provider_key"),
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


def _parse_observed_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("OBSERVED_AT_MUST_BE_TIMEZONE_AWARE")
    return parsed


def _rollback_quietly(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _expected_sequence_state(
    *,
    sequence_id: int,
    observed_at: datetime,
    prior_sequence_ids: list[int],
    prior_observed_at: list[datetime],
) -> tuple[str, tuple[str, ...], bool]:
    if prior_sequence_ids and sequence_id < max(prior_sequence_ids):
        return (
            SEQUENCE_OUT_OF_ORDER,
            (REASON_OUT_OF_ORDER,),
            False,
        )

    if prior_observed_at and observed_at < max(prior_observed_at):
        return (
            SEQUENCE_LATE_OBSERVATION,
            (REASON_OBSERVED_AT_REGRESSION,),
            False,
        )

    return (
        SEQUENCE_ACCEPTED,
        (REASON_SEQUENCE_MONOTONIC,),
        True,
    )


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
    provider_key: str | None
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
            provider_key=None,
            subject_key=None,
            correlation_id=None,
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=None,
        )

    providers = {item.provider_key for item in items}
    subjects = {item.subject_key for item in items}
    correlations = {item.correlation_id for item in items}
    modalities = {item.modality for item in items}

    if len(providers) != 1:
        reasons.append("PROVIDER_KEY_MISMATCH")
    if len(subjects) != 1:
        reasons.append("SUBJECT_IDENTITY_MISMATCH")
    if len(modalities) < 2:
        reasons.append("DISTINCT_MODALITIES_REQUIRED")
    if len(correlations) != 1:
        reasons.append("CORRELATION_ID_MISMATCH")

    if reasons:
        return FootballCrossModalAlignment(
            status=ALIGNMENT_BLOCKED,
            reason_codes=tuple(reasons),
            provider_key=(
                None if len(providers) != 1 else next(iter(providers))
            ),
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
            provider_key=next(iter(providers)),
            subject_key=next(iter(subjects)),
            correlation_id=next(iter(correlations)),
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=skew_ms,
        )

    if skew_ms > tolerance:
        return FootballCrossModalAlignment(
            status=ALIGNMENT_BLOCKED,
            reason_codes=("CROSS_MODAL_SKEW_EXCEEDED",),
            provider_key=next(iter(providers)),
            subject_key=next(iter(subjects)),
            correlation_id=next(iter(correlations)),
            modalities=tuple(sorted({item.modality for item in items})),
            max_observed_at_skew_ms=skew_ms,
        )

    return FootballCrossModalAlignment(
        status=ALIGNMENT_PASS,
        reason_codes=("CROSS_MODAL_ALIGNMENT_WITHIN_EXPLICIT_POLICY",),
        provider_key=next(iter(providers)),
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
    duplicate_of_fingerprint: str | None = None


SEQUENCE_MISSING_EVIDENCE = "MISSING_DURABLE_EVIDENCE"
REASON_DURABLE_EVIDENCE_MISSING = "DURABLE_SEQUENCE_EVIDENCE_MISSING"
REASON_DURABLE_EVIDENCE_INVALID = "DURABLE_SEQUENCE_EVIDENCE_INVALID"


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
                    provider_key TEXT,
                    modality TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    sequence_id INTEGER NOT NULL,
                    observed_at TEXT,
                    source_record_fingerprint TEXT,
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
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(football_live_observation)"
                ).fetchall()
            }
            for column, ddl in (
                ("provider_key", "TEXT"),
                ("observed_at", "TEXT"),
                ("source_record_fingerprint", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(
                        "ALTER TABLE football_live_observation "
                        f"ADD COLUMN {column} {ddl}"
                    )

            rows = connection.execute(
                """
                SELECT observation_fingerprint, payload_json
                FROM football_live_observation
                WHERE provider_key IS NULL
                   OR observed_at IS NULL
                   OR source_record_fingerprint IS NULL
                """
            ).fetchall()
            for observation_fp, payload_json in rows:
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue
                connection.execute(
                    """
                    UPDATE football_live_observation
                    SET provider_key = COALESCE(provider_key, ?),
                        observed_at = COALESCE(observed_at, ?),
                        source_record_fingerprint = COALESCE(
                            source_record_fingerprint,
                            ?
                        )
                    WHERE observation_fingerprint = ?
                    """,
                    (
                        payload.get("provider_key"),
                        payload.get("observed_at"),
                        payload.get("source_record_fingerprint"),
                        observation_fp,
                    ),
                )

            connection.execute(
                "DROP INDEX IF EXISTS ux_football_live_source_record"
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    ux_football_live_source_record_v2
                ON football_live_observation (
                    subject_key,
                    provider_key,
                    modality,
                    correlation_id,
                    source_record_fingerprint
                )
                WHERE provider_key IS NOT NULL
                  AND source_record_fingerprint IS NOT NULL
                """
            )

    @staticmethod
    def _row_select_sql() -> str:
        return """
            SELECT
                rowid,
                observation_fingerprint,
                subject_key,
                provider_key,
                modality,
                correlation_id,
                sequence_id,
                observed_at,
                source_record_fingerprint,
                status,
                reason_codes_json,
                payload_json,
                payload_sha256
            FROM football_live_observation
        """

    def _validate_row(
        self,
        connection: sqlite3.Connection,
        row: tuple[Any, ...],
    ) -> FootballLiveSequenceDecision:
        if len(row) != 13:
            raise ValueError("LIVE_EVIDENCE_COLUMN_COUNT_INVALID")

        (
            rowid,
            observation_fp,
            subject_key,
            provider_key,
            modality,
            correlation_id,
            sequence_id,
            observed_at_text,
            source_record_fp,
            status,
            reasons_json,
            payload_json,
            stored_sha,
        ) = row

        if sha256(payload_json.encode("utf-8")).hexdigest() != stored_sha:
            raise ValueError("LIVE_EVIDENCE_PAYLOAD_HASH_MISMATCH")

        try:
            payload = json.loads(payload_json)
            reason_values = json.loads(reasons_json)
            observed_at = _parse_observed_at(str(observed_at_text))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError("LIVE_EVIDENCE_PAYLOAD_INVALID") from error

        if payload.get("observation_fingerprint") != observation_fp:
            raise ValueError("LIVE_EVIDENCE_FINGERPRINT_COLUMN_MISMATCH")
        if _expected_observation_fingerprint(payload) != observation_fp:
            raise ValueError("LIVE_EVIDENCE_FINGERPRINT_REDERIVATION_FAILED")
        if payload.get("sport") != "football":
            raise ValueError("LIVE_EVIDENCE_SPORT_INVALID")
        if payload.get("subject_key") != subject_key:
            raise ValueError("LIVE_EVIDENCE_SUBJECT_COLUMN_MISMATCH")
        if payload.get("provider_key") != provider_key:
            raise ValueError("LIVE_EVIDENCE_PROVIDER_COLUMN_MISMATCH")
        if payload.get("modality") != modality:
            raise ValueError("LIVE_EVIDENCE_MODALITY_COLUMN_MISMATCH")
        if payload.get("correlation_id") != correlation_id:
            raise ValueError("LIVE_EVIDENCE_CORRELATION_COLUMN_MISMATCH")
        if payload.get("sequence_id") != sequence_id:
            raise ValueError("LIVE_EVIDENCE_SEQUENCE_COLUMN_MISMATCH")
        if payload.get("observed_at") != observed_at_text:
            raise ValueError("LIVE_EVIDENCE_OBSERVED_AT_COLUMN_MISMATCH")
        if payload.get("source_record_fingerprint") != source_record_fp:
            raise ValueError("LIVE_EVIDENCE_SOURCE_COLUMN_MISMATCH")
        if not isinstance(reason_values, list) or not reason_values:
            raise ValueError("LIVE_EVIDENCE_REASON_CODES_INVALID")

        prior_rows = connection.execute(
            """
            SELECT sequence_id, observed_at
            FROM football_live_observation
            WHERE subject_key = ?
              AND provider_key = ?
              AND modality = ?
              AND correlation_id = ?
              AND rowid < ?
            ORDER BY rowid
            """,
            (
                subject_key,
                provider_key,
                modality,
                correlation_id,
                rowid,
            ),
        ).fetchall()
        prior_sequence_ids = [int(item[0]) for item in prior_rows]
        prior_observed_at = [
            _parse_observed_at(str(item[1]))
            for item in prior_rows
            if item[1] is not None
        ]
        expected_status, expected_reasons, expected_accepted = (
            _expected_sequence_state(
                sequence_id=int(sequence_id),
                observed_at=observed_at,
                prior_sequence_ids=prior_sequence_ids,
                prior_observed_at=prior_observed_at,
            )
        )
        if status != expected_status:
            raise ValueError("LIVE_EVIDENCE_STATUS_REDERIVATION_FAILED")
        if tuple(reason_values) != expected_reasons:
            raise ValueError("LIVE_EVIDENCE_REASON_REDERIVATION_FAILED")

        return FootballLiveSequenceDecision(
            observation_fingerprint=str(observation_fp),
            sequence_id=int(sequence_id),
            status=str(status),
            reason_codes=tuple(str(item) for item in reason_values),
            idempotent=True,
            accepted_for_fusion=expected_accepted,
        )

    def record(
        self,
        observation: LiveTemporalObservation,
    ) -> FootballLiveSequenceDecision:
        if observation.sport != "football":
            raise ValueError("FOOTBALL_LIVE_SPORT_REQUIRED")
        if observation.source_record_fingerprint is None:
            raise ValueError(
                "SOURCE_RECORD_FINGERPRINT_REQUIRED_FOR_REPEATABLE_LIVE"
            )

        payload_json = _canonical(observation.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")

                existing = connection.execute(
                    self._row_select_sql()
                    + """
                    WHERE subject_key = ?
                      AND provider_key = ?
                      AND modality = ?
                      AND correlation_id = ?
                      AND sequence_id = ?
                    """,
                    (
                        observation.subject_key,
                        observation.provider_key,
                        observation.modality,
                        observation.correlation_id,
                        observation.sequence_id,
                    ),
                ).fetchone()

                if existing is not None:
                    decision = self._validate_row(connection, existing)
                    if (
                        decision.observation_fingerprint
                        != observation.observation_fingerprint
                    ):
                        raise ValueError("LIVE_SEQUENCE_MUTATION_VIOLATION")
                    connection.execute("COMMIT")
                    return decision

                source_fp = observation.source_record_fingerprint
                duplicate = connection.execute(
                    self._row_select_sql()
                    + """
                    WHERE subject_key = ?
                      AND provider_key = ?
                      AND modality = ?
                      AND correlation_id = ?
                      AND source_record_fingerprint = ?
                    """,
                    (
                        observation.subject_key,
                        observation.provider_key,
                        observation.modality,
                        observation.correlation_id,
                        source_fp,
                    ),
                ).fetchone()
                if duplicate is not None:
                    duplicate_decision = self._validate_row(
                        connection,
                        duplicate,
                    )
                    connection.execute("COMMIT")
                    return FootballLiveSequenceDecision(
                        observation_fingerprint=(
                            observation.observation_fingerprint
                        ),
                        sequence_id=observation.sequence_id,
                        status=SEQUENCE_DUPLICATE_SOURCE,
                        reason_codes=(REASON_SOURCE_ALREADY_SEEN,),
                        idempotent=True,
                        accepted_for_fusion=False,
                        duplicate_of_fingerprint=(
                            duplicate_decision.observation_fingerprint
                        ),
                    )

                prior_rows = connection.execute(
                    """
                    SELECT sequence_id, observed_at
                    FROM football_live_observation
                    WHERE subject_key = ?
                      AND provider_key = ?
                      AND modality = ?
                      AND correlation_id = ?
                    ORDER BY rowid
                    """,
                    (
                        observation.subject_key,
                        observation.provider_key,
                        observation.modality,
                        observation.correlation_id,
                    ),
                ).fetchall()

                prior_sequence_ids = [int(row[0]) for row in prior_rows]
                prior_observed_at = [
                    _parse_observed_at(str(row[1]))
                    for row in prior_rows
                    if row[1] is not None
                ]
                status, reasons, accepted = _expected_sequence_state(
                    sequence_id=observation.sequence_id,
                    observed_at=observation.observed_at,
                    prior_sequence_ids=prior_sequence_ids,
                    prior_observed_at=prior_observed_at,
                )

                connection.execute(
                    """
                    INSERT INTO football_live_observation (
                        observation_fingerprint,
                        subject_key,
                        provider_key,
                        modality,
                        correlation_id,
                        sequence_id,
                        observed_at,
                        source_record_fingerprint,
                        status,
                        reason_codes_json,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_fingerprint,
                        observation.subject_key,
                        observation.provider_key,
                        observation.modality,
                        observation.correlation_id,
                        observation.sequence_id,
                        observation.observed_at.isoformat(),
                        source_fp,
                        status,
                        _canonical(list(reasons)),
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                _rollback_quietly(connection)
                raise

        return FootballLiveSequenceDecision(
            observation_fingerprint=observation.observation_fingerprint,
            sequence_id=observation.sequence_id,
            status=status,
            reason_codes=reasons,
            idempotent=False,
            accepted_for_fusion=accepted,
        )

    def verify_for_fusion(
        self,
        observation: LiveTemporalObservation,
    ) -> FootballLiveSequenceDecision:
        if observation.source_record_fingerprint is None:
            return FootballLiveSequenceDecision(
                observation_fingerprint=observation.observation_fingerprint,
                sequence_id=observation.sequence_id,
                status=SEQUENCE_MISSING_EVIDENCE,
                reason_codes=(REASON_DURABLE_EVIDENCE_MISSING,),
                idempotent=False,
                accepted_for_fusion=False,
            )

        with self._connect() as connection:
            row = connection.execute(
                self._row_select_sql()
                + """
                WHERE subject_key = ?
                  AND provider_key = ?
                  AND modality = ?
                  AND correlation_id = ?
                  AND sequence_id = ?
                """,
                (
                    observation.subject_key,
                    observation.provider_key,
                    observation.modality,
                    observation.correlation_id,
                    observation.sequence_id,
                ),
            ).fetchone()
            if row is None:
                return FootballLiveSequenceDecision(
                    observation_fingerprint=(
                        observation.observation_fingerprint
                    ),
                    sequence_id=observation.sequence_id,
                    status=SEQUENCE_MISSING_EVIDENCE,
                    reason_codes=(REASON_DURABLE_EVIDENCE_MISSING,),
                    idempotent=False,
                    accepted_for_fusion=False,
                )
            decision = self._validate_row(connection, row)
            if (
                decision.observation_fingerprint
                != observation.observation_fingerprint
            ):
                raise ValueError("LIVE_SEQUENCE_MUTATION_VIOLATION")
            return decision

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                self._row_select_sql() + " ORDER BY rowid"
            ).fetchall()

            seen_sources: set[
                tuple[str, str, str, str, str]
            ] = set()
            for row in rows:
                try:
                    decision = self._validate_row(connection, row)
                except ValueError:
                    return False

                source_record_fp = row[8]
                if source_record_fp is None:
                    return False
                source_key = (
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[5]),
                    str(source_record_fp),
                )
                if source_key in seen_sources:
                    return False
                seen_sources.add(source_key)

                if (
                    decision.status not in {
                        SEQUENCE_ACCEPTED,
                        SEQUENCE_OUT_OF_ORDER,
                        SEQUENCE_LATE_OBSERVATION,
                    }
                ):
                    return False
            return True


@dataclass(frozen=True)
class FootballRepeatableLiveAdmission:
    status: str
    reason_codes: tuple[str, ...]
    freshness: tuple[FootballLiveFreshnessDecision, ...]
    alignment: FootballCrossModalAlignment
    sequence_evidence: tuple[FootballLiveSequenceDecision, ...]
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
    evidence_store: SQLiteFootballLiveObservationStore,
) -> FootballRepeatableLiveAdmission:
    items = tuple(observations)
    if len(items) < 2:
        raise ValueError("REPEATABLE_LIVE_ADMISSION_REQUIRES_MULTIMODAL_INPUT")

    freshness = tuple(
        evaluate_football_live_freshness(item, policy)
        for item in items
    )
    alignment = evaluate_football_cross_modal_alignment(items, policy)

    sequence_evidence: list[FootballLiveSequenceDecision] = []
    sequence_integrity_failed = False
    for item in items:
        try:
            decision = evidence_store.verify_for_fusion(item)
        except ValueError:
            decision = FootballLiveSequenceDecision(
                observation_fingerprint=item.observation_fingerprint,
                sequence_id=item.sequence_id,
                status=SEQUENCE_MISSING_EVIDENCE,
                reason_codes=(REASON_DURABLE_EVIDENCE_INVALID,),
                idempotent=False,
                accepted_for_fusion=False,
            )
            sequence_integrity_failed = True
        sequence_evidence.append(decision)

    reasons: list[str] = []
    for decision in freshness:
        reasons.extend(decision.reason_codes)
    reasons.extend(alignment.reason_codes)
    for decision in sequence_evidence:
        if not decision.accepted_for_fusion:
            reasons.extend(decision.reason_codes)

    if (
        sequence_integrity_failed
        or any(
            not decision.accepted_for_fusion
            for decision in sequence_evidence
        )
        or any(item.status == FRESHNESS_BLOCKED for item in freshness)
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
        sequence_evidence=tuple(sequence_evidence),
    )
