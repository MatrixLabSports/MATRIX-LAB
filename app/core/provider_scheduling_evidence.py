from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_scheduling_authorization import (
    ProviderSchedulingAuthorization,
)


_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_STATUSES = {"AUTHORIZED", "BLOCKED", "EMPTY_QUEUE"}


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


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    return value.lower()


@dataclass(frozen=True)
class ProviderSchedulingEvidence:
    evidence_id: str
    sport: str
    authorization_status: str
    execution_eligible: bool
    queue_fingerprint: str
    authorization_fingerprint: str


@dataclass(frozen=True)
class ProviderSchedulingEvidenceIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderSchedulingEvidenceLedger:
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
                CREATE TABLE IF NOT EXISTS provider_scheduling_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    authorization_status TEXT NOT NULL,
                    execution_eligible INTEGER NOT NULL,
                    queue_fingerprint TEXT NOT NULL,
                    authorization_fingerprint TEXT NOT NULL UNIQUE,
                    decision_fingerprints_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (
                        authorization_status IN (
                            'AUTHORIZED',
                            'BLOCKED',
                            'EMPTY_QUEUE'
                        )
                    ),
                    CHECK (execution_eligible IN (0, 1))
                )
                """
            )

    @staticmethod
    def evidence_id_for(
        authorization: ProviderSchedulingAuthorization,
    ) -> str:
        payload = {
            "schema": "matrix.provider-scheduling-evidence-id/2",
            "sport": authorization.sport,
            "authorization_status": authorization.authorization_status,
            "execution_eligible": authorization.execution_eligible,
            "queue_fingerprint": authorization.queue_fingerprint,
            "authorization_fingerprint": (
                authorization.authorization_fingerprint
            ),
            "decision_fingerprints": list(
                authorization.decision_fingerprints
            ),
        }
        return _sha256_text(_canonical_json(payload))

    @staticmethod
    def _validate_authorization_shape(
        authorization: ProviderSchedulingAuthorization,
    ) -> tuple[str, str, tuple[str, ...]]:
        if authorization.sport not in _ALLOWED_SPORTS:
            raise ValueError("INVALID_SPORT")

        if authorization.authorization_status not in _ALLOWED_STATUSES:
            raise ValueError("INVALID_AUTHORIZATION_STATUS")

        expected_eligible = authorization.authorization_status in {
            "AUTHORIZED",
            "EMPTY_QUEUE",
        }
        if authorization.execution_eligible is not expected_eligible:
            raise ValueError("SCHEDULING_ELIGIBILITY_MISMATCH")

        queue_fp = _validate_hex64(
            "QUEUE_FINGERPRINT",
            authorization.queue_fingerprint,
        )
        authorization_fp = _validate_hex64(
            "AUTHORIZATION_FINGERPRINT",
            authorization.authorization_fingerprint,
        )

        decision_fingerprints = tuple(
            _validate_hex64("DECISION_FINGERPRINT", value)
            for value in authorization.decision_fingerprints
        )

        if len(decision_fingerprints) != len(
            set(decision_fingerprints)
        ):
            raise ValueError("DUPLICATE_DECISION_FINGERPRINT")

        if authorization.authorization_status == "EMPTY_QUEUE":
            if authorization.provider_keys:
                raise ValueError("EMPTY_QUEUE_WITH_PROVIDERS")
            if authorization.queue_item_fingerprints:
                raise ValueError("EMPTY_QUEUE_WITH_ITEMS")
            if decision_fingerprints:
                raise ValueError("EMPTY_QUEUE_WITH_DECISIONS")

        if authorization.authorization_status == "AUTHORIZED":
            if not authorization.provider_keys:
                raise ValueError("AUTHORIZED_WITHOUT_PROVIDERS")

            if set(authorization.provider_keys) != set(
                authorization.eligible_provider_keys
            ):
                raise ValueError("AUTHORIZED_PROVIDER_SET_MISMATCH")

            if authorization.blocked_provider_keys:
                raise ValueError("AUTHORIZED_WITH_BLOCKED_PROVIDER")

            if authorization.missing_provider_keys:
                raise ValueError("AUTHORIZED_WITH_MISSING_PROVIDER")

        return queue_fp, authorization_fp, decision_fingerprints

    @staticmethod
    def _verify_durable_health_evidence(
        *,
        authorization: ProviderSchedulingAuthorization,
        decision_fingerprints: tuple[str, ...],
        health_evidence_ledger: SQLiteProviderHealthEvidenceLedger,
    ) -> None:
        health_integrity = health_evidence_ledger.audit_integrity()
        if not health_integrity.ok:
            raise ValueError("HEALTH_EVIDENCE_INTEGRITY_FAILED")

        durable_by_provider: dict[str, Mapping[str, Any]] = {}

        for decision_fp in decision_fingerprints:
            payload = health_evidence_ledger.get_by_decision_fingerprint(
                decision_fp
            )

            if payload is None:
                raise ValueError(
                    f"MISSING_DURABLE_HEALTH_EVIDENCE:{decision_fp}"
                )

            if payload.get("sport") != authorization.sport:
                raise ValueError("SPORT_BOUNDARY_VIOLATION")

            provider_key = payload.get("provider_key")
            if (
                not isinstance(provider_key, str)
                or provider_key not in authorization.provider_keys
            ):
                raise ValueError("HEALTH_EVIDENCE_PROVIDER_MISMATCH")

            if provider_key in durable_by_provider:
                raise ValueError(
                    "MULTIPLE_HEALTH_DECISIONS_FOR_PROVIDER"
                )

            durable_by_provider[provider_key] = payload

        if authorization.authorization_status == "AUTHORIZED":
            if set(durable_by_provider) != set(
                authorization.provider_keys
            ):
                raise ValueError(
                    "AUTHORIZED_WITHOUT_COMPLETE_DURABLE_HEALTH_EVIDENCE"
                )

            for provider_key in authorization.provider_keys:
                payload = durable_by_provider[provider_key]

                if payload.get("decision_status") != "ELIGIBLE":
                    raise ValueError(
                        f"AUTHORIZED_PROVIDER_NOT_ELIGIBLE:{provider_key}"
                    )

                if payload.get("scheduling_eligible") is not True:
                    raise ValueError(
                        f"AUTHORIZED_PROVIDER_NOT_SCHEDULABLE:{provider_key}"
                    )

                if payload.get("automatic_provider_switch") is not False:
                    raise ValueError(
                        "HEALTH_EVIDENCE_AUTO_SWITCH_ENABLED"
                    )

    def record_authorization(
        self,
        *,
        authorization: ProviderSchedulingAuthorization,
        health_evidence_ledger: SQLiteProviderHealthEvidenceLedger,
    ) -> ProviderSchedulingEvidence:
        (
            queue_fp,
            authorization_fp,
            decision_fingerprints,
        ) = self._validate_authorization_shape(authorization)

        self._verify_durable_health_evidence(
            authorization=authorization,
            decision_fingerprints=decision_fingerprints,
            health_evidence_ledger=health_evidence_ledger,
        )

        payload = dict(authorization.payload())

        if payload.get("queue_fingerprint") != queue_fp:
            raise ValueError("QUEUE_FINGERPRINT_PAYLOAD_MISMATCH")

        if (
            payload.get("authorization_fingerprint")
            != authorization_fp
        ):
            raise ValueError(
                "AUTHORIZATION_FINGERPRINT_PAYLOAD_MISMATCH"
            )

        if payload.get("automatic_provider_switch") is not False:
            raise ValueError("AUTO_PROVIDER_SWITCH_ENABLED")

        if payload.get("automatic_wagering") is not False:
            raise ValueError("AUTO_WAGERING_ENABLED")

        payload_json = _canonical_json(payload)
        payload_sha = _sha256_text(payload_json)
        evidence_id = self.evidence_id_for(authorization)
        decisions_json = _canonical_json(
            list(decision_fingerprints)
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    payload_sha256
                FROM provider_scheduling_evidence
                WHERE authorization_fingerprint = ?
                """,
                (authorization_fp,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return ProviderSchedulingEvidence(
                        evidence_id=evidence_id,
                        sport=authorization.sport,
                        authorization_status=(
                            authorization.authorization_status
                        ),
                        execution_eligible=(
                            authorization.execution_eligible
                        ),
                        queue_fingerprint=queue_fp,
                        authorization_fingerprint=authorization_fp,
                    )

                raise ValueError(
                    "PROVIDER_SCHEDULING_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO provider_scheduling_evidence (
                        evidence_id,
                        sport,
                        authorization_status,
                        execution_eligible,
                        queue_fingerprint,
                        authorization_fingerprint,
                        decision_fingerprints_json,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        authorization.sport,
                        authorization.authorization_status,
                        int(authorization.execution_eligible),
                        queue_fp,
                        authorization_fp,
                        decisions_json,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "PROVIDER_SCHEDULING_APPEND_ONLY_VIOLATION"
                ) from error

        return ProviderSchedulingEvidence(
            evidence_id=evidence_id,
            sport=authorization.sport,
            authorization_status=authorization.authorization_status,
            execution_eligible=authorization.execution_eligible,
            queue_fingerprint=queue_fp,
            authorization_fingerprint=authorization_fp,
        )

    def get_by_authorization_fingerprint(
        self,
        authorization_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        validated = _validate_hex64(
            "AUTHORIZATION_FINGERPRINT",
            authorization_fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM provider_scheduling_evidence
                WHERE authorization_fingerprint = ?
                """,
                (validated,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def audit_integrity(
        self,
    ) -> ProviderSchedulingEvidenceIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    authorization_status,
                    execution_eligible,
                    queue_fingerprint,
                    authorization_fingerprint,
                    decision_fingerprints_json,
                    payload_json,
                    payload_sha256
                FROM provider_scheduling_evidence
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            sport,
            authorization_status,
            execution_eligible,
            queue_fp,
            authorization_fp,
            decision_fingerprints_json,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
                decision_fingerprints = json.loads(
                    decision_fingerprints_json
                )
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{authorization_fp}"
                )
                continue

            canonical = _canonical_json(payload)
            actual_sha = _sha256_text(canonical)

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{authorization_fp}"
                )

            expected_pairs = {
                "sport": sport,
                "authorization_status": authorization_status,
                "execution_eligible": bool(execution_eligible),
                "queue_fingerprint": queue_fp,
                "authorization_fingerprint": authorization_fp,
                "decision_fingerprints": decision_fingerprints,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:{authorization_fp}"
                    )

            expected_evidence = _sha256_text(
                _canonical_json(
                    {
                        "schema": (
                            "matrix.provider-scheduling-evidence-id/2"
                        ),
                        "sport": sport,
                        "authorization_status": authorization_status,
                        "execution_eligible": bool(execution_eligible),
                        "queue_fingerprint": queue_fp,
                        "authorization_fingerprint": authorization_fp,
                        "decision_fingerprints": decision_fingerprints,
                    }
                )
            )

            if evidence_id != expected_evidence:
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:{authorization_fp}"
                )

            expected_eligible = authorization_status in {
                "AUTHORIZED",
                "EMPTY_QUEUE",
            }
            if bool(execution_eligible) != expected_eligible:
                errors.append(
                    f"ELIGIBILITY_MISMATCH:{authorization_fp}"
                )

            if payload.get("automatic_provider_switch") is not False:
                errors.append(
                    f"AUTO_SWITCH_ENABLED:{authorization_fp}"
                )

            if payload.get("automatic_wagering") is not False:
                errors.append(
                    f"AUTO_WAGERING_ENABLED:{authorization_fp}"
                )

        return ProviderSchedulingEvidenceIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
