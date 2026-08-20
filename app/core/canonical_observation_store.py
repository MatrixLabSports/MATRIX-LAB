from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.point_in_time_admission_evidence import (
    SQLitePointInTimeAdmissionEvidenceLedger,
)
from app.core.point_in_time_data_contract import (
    PointInTimeAdmissionDecision,
    PointInTimeDataRecord,
    build_point_in_time_record,
)


UTC = timezone.utc


def _canonical_json(value: Any) -> str:
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
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("INVALID_STORED_TIMESTAMP")
    return parsed.astimezone(UTC)


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class CanonicalObservation:
    observation_id: str
    sport: str
    entity_type: str
    canonical_id: str
    schema_name: str
    schema_version: str
    transformation_version: str
    observed_at: datetime
    available_at: datetime
    record_fingerprint: str
    admission_decision_fingerprint: str
    admission_evidence_id: str
    payload: Mapping[str, Any]

    def evidence_payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.canonical-observation/1",
            "observation_id": self.observation_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "transformation_version": self.transformation_version,
            "observed_at": _iso(self.observed_at),
            "available_at": _iso(self.available_at),
            "record_fingerprint": self.record_fingerprint,
            "admission_decision_fingerprint": (
                self.admission_decision_fingerprint
            ),
            "admission_evidence_id": self.admission_evidence_id,
            "payload": dict(self.payload),
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class CanonicalObservationIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteCanonicalObservationStore:
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
                CREATE TABLE IF NOT EXISTS canonical_observations (
                    observation_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    provider_entity_id TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    transformation_version TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    record_fingerprint TEXT NOT NULL UNIQUE,
                    admission_decision_fingerprint TEXT NOT NULL UNIQUE,
                    admission_evidence_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_canonical_observations_as_of
                ON canonical_observations (
                    sport,
                    canonical_id,
                    schema_name,
                    available_at,
                    observed_at
                )
                """
            )

    @staticmethod
    def _validate_record_derivation(
        record: PointInTimeDataRecord,
    ) -> None:
        expected = build_point_in_time_record(
            sport=record.sport,
            entity_type=record.entity_type,
            canonical_id=record.canonical_id,
            provider_key=record.provider_key,
            provider_entity_id=record.provider_entity_id,
            source_record_id=record.source_record_id,
            schema_name=record.schema_name,
            schema_version=record.schema_version,
            transformation_version=record.transformation_version,
            observed_at=record.observed_at,
            available_at=record.available_at,
            payload=record.payload,
        )

        if expected != record:
            raise ValueError(
                "POINT_IN_TIME_RECORD_DERIVATION_MISMATCH"
            )

    def append_admitted_record(
        self,
        *,
        record: PointInTimeDataRecord,
        decision: PointInTimeAdmissionDecision,
        admission_evidence_ledger: (
            SQLitePointInTimeAdmissionEvidenceLedger
        ),
    ) -> CanonicalObservation:
        self._validate_record_derivation(record)

        if decision.decision_status != "ADMIT":
            raise ValueError("RECORD_NOT_ADMITTED")

        if decision.downstream_eligible is not True:
            raise ValueError("RECORD_NOT_DOWNSTREAM_ELIGIBLE")

        if decision.sport != record.sport:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if decision.canonical_id != record.canonical_id:
            raise ValueError("CANONICAL_ID_MISMATCH")

        if (
            decision.record_fingerprint
            != record.record_fingerprint
        ):
            raise ValueError("RECORD_FINGERPRINT_MISMATCH")

        evidence_integrity = (
            admission_evidence_ledger.audit_integrity()
        )
        if not evidence_integrity.ok:
            raise ValueError(
                "ADMISSION_EVIDENCE_INTEGRITY_FAILED"
            )

        evidence = (
            admission_evidence_ledger
            .get_by_decision_fingerprint(
                decision.decision_fingerprint
            )
        )

        if evidence is None:
            raise ValueError(
                "MISSING_DURABLE_ADMISSION_EVIDENCE"
            )

        if evidence.get("decision_status") != "ADMIT":
            raise ValueError(
                "DURABLE_EVIDENCE_NOT_ADMITTED"
            )

        if evidence.get("downstream_eligible") is not True:
            raise ValueError(
                "DURABLE_EVIDENCE_NOT_DOWNSTREAM_ELIGIBLE"
            )

        if evidence.get("sport") != record.sport:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if evidence.get("canonical_id") != record.canonical_id:
            raise ValueError(
                "DURABLE_CANONICAL_ID_MISMATCH"
            )

        if (
            evidence.get("record_fingerprint")
            != record.record_fingerprint
        ):
            raise ValueError(
                "DURABLE_RECORD_FINGERPRINT_MISMATCH"
            )

        decision_fp = _validate_hex64(
            "ADMISSION_DECISION_FINGERPRINT",
            decision.decision_fingerprint,
        )

        evidence_id = SQLitePointInTimeAdmissionEvidenceLedger.evidence_id_for(
            decision
        )

        observation_id = _sha(
            {
                "schema": "matrix.canonical-observation-id/1",
                "record_fingerprint": record.record_fingerprint,
                "admission_decision_fingerprint": decision_fp,
                "admission_evidence_id": evidence_id,
            }
        )

        observation = CanonicalObservation(
            observation_id=observation_id,
            sport=record.sport,
            entity_type=record.entity_type,
            canonical_id=record.canonical_id,
            schema_name=record.schema_name,
            schema_version=record.schema_version,
            transformation_version=record.transformation_version,
            observed_at=record.observed_at,
            available_at=record.available_at,
            record_fingerprint=record.record_fingerprint,
            admission_decision_fingerprint=decision_fp,
            admission_evidence_id=evidence_id,
            payload=dict(record.payload),
        )

        payload_json = _canonical_json(
            observation.evidence_payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    observation_id,
                    payload_sha256
                FROM canonical_observations
                WHERE record_fingerprint = ?
                """,
                (record.record_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == observation_id
                    and str(existing[1]) == payload_sha
                ):
                    return observation

                raise ValueError(
                    "CANONICAL_OBSERVATION_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO canonical_observations (
                        observation_id,
                        sport,
                        entity_type,
                        canonical_id,
                        provider_key,
                        provider_entity_id,
                        source_record_id,
                        schema_name,
                        schema_version,
                        transformation_version,
                        observed_at,
                        available_at,
                        record_fingerprint,
                        admission_decision_fingerprint,
                        admission_evidence_id,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        record.sport,
                        record.entity_type,
                        record.canonical_id,
                        record.provider_key,
                        record.provider_entity_id,
                        record.source_record_id,
                        record.schema_name,
                        record.schema_version,
                        record.transformation_version,
                        _iso(record.observed_at),
                        _iso(record.available_at),
                        record.record_fingerprint,
                        decision_fp,
                        evidence_id,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "CANONICAL_OBSERVATION_APPEND_ONLY_VIOLATION"
                ) from error

        return observation

    def get_by_record_fingerprint(
        self,
        record_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        record_fingerprint = _validate_hex64(
            "RECORD_FINGERPRINT",
            record_fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM canonical_observations
                WHERE record_fingerprint = ?
                """,
                (record_fingerprint,),
            ).fetchone()

        return None if row is None else json.loads(row[0])

    def list_as_of(
        self,
        *,
        sport: str,
        canonical_id: str,
        schema_name: str,
        as_of: datetime,
        schema_version: str | None = None,
        limit: int | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")

        if not isinstance(canonical_id, str) or not canonical_id:
            raise ValueError("INVALID_CANONICAL_ID")

        if not isinstance(schema_name, str) or not schema_name:
            raise ValueError("INVALID_SCHEMA_NAME")

        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("INVALID_AS_OF")

        if limit is not None and (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit <= 0
        ):
            raise ValueError("INVALID_LIMIT")

        clauses = [
            "sport = ?",
            "canonical_id = ?",
            "schema_name = ?",
            "available_at <= ?",
        ]
        params: list[Any] = [
            sport,
            canonical_id,
            schema_name,
            _iso(as_of),
        ]

        if schema_version is not None:
            clauses.append("schema_version = ?")
            params.append(schema_version)

        sql = f"""
            SELECT payload_json
            FROM canonical_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY
                observed_at DESC,
                available_at DESC,
                record_fingerprint ASC
        """

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                sql,
                tuple(params),
            ).fetchall()

        return tuple(json.loads(row[0]) for row in rows)

    def audit_integrity(
        self,
    ) -> CanonicalObservationIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observation_id,
                    sport,
                    entity_type,
                    canonical_id,
                    schema_name,
                    schema_version,
                    transformation_version,
                    observed_at,
                    available_at,
                    record_fingerprint,
                    admission_decision_fingerprint,
                    admission_evidence_id,
                    payload_json,
                    payload_sha256
                FROM canonical_observations
                ORDER BY created_at, observation_id
                """
            ).fetchall()

        for row in rows:
            (
                observation_id,
                sport,
                entity_type,
                canonical_id,
                schema_name,
                schema_version,
                transformation_version,
                observed_at,
                available_at,
                record_fingerprint,
                decision_fingerprint,
                evidence_id,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{observation_id}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()
            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{observation_id}"
                )

            expected_pairs = {
                "observation_id": observation_id,
                "sport": sport,
                "entity_type": entity_type,
                "canonical_id": canonical_id,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "transformation_version": transformation_version,
                "observed_at": observed_at,
                "available_at": available_at,
                "record_fingerprint": record_fingerprint,
                "admission_decision_fingerprint": (
                    decision_fingerprint
                ),
                "admission_evidence_id": evidence_id,
                "missing_is_zero": False,
                "name_join_used": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{observation_id}"
                    )

            try:
                observed = _parse_utc(observed_at)
                available = _parse_utc(available_at)
            except ValueError:
                errors.append(
                    f"INVALID_TIMESTAMP:{observation_id}"
                )
                continue

            if available < observed:
                errors.append(
                    f"AVAILABLE_BEFORE_OBSERVED:"
                    f"{observation_id}"
                )

            expected_observation_id = _sha(
                {
                    "schema": (
                        "matrix.canonical-observation-id/1"
                    ),
                    "record_fingerprint": record_fingerprint,
                    "admission_decision_fingerprint": (
                        decision_fingerprint
                    ),
                    "admission_evidence_id": evidence_id,
                }
            )

            if observation_id != expected_observation_id:
                errors.append(
                    f"OBSERVATION_ID_MISMATCH:"
                    f"{observation_id}"
                )

        return CanonicalObservationIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
