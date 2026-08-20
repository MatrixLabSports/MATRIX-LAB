from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.point_in_time_data_contract import (
    PointInTimeAdmissionDecision,
    compute_point_in_time_admission_decision_fingerprint,
)


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


def _iso(value) -> str:
    return (
        value.isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class PointInTimeAdmissionEvidence:
    evidence_id: str
    sport: str
    canonical_id: str
    decision_status: str
    downstream_eligible: bool
    record_fingerprint: str
    decision_fingerprint: str


@dataclass(frozen=True)
class PointInTimeAdmissionEvidenceIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLitePointInTimeAdmissionEvidenceLedger:
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
                CREATE TABLE IF NOT EXISTS point_in_time_admission_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    record_fingerprint TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    decision_status TEXT NOT NULL,
                    downstream_eligible INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (
                        decision_status IN ('ADMIT', 'QUARANTINE')
                    ),
                    CHECK (downstream_eligible IN (0, 1))
                )
                """
            )

    @staticmethod
    def _validate_decision(
        decision: PointInTimeAdmissionDecision,
    ) -> None:
        expected_eligible = (
            decision.decision_status == "ADMIT"
        )

        if decision.decision_status not in {
            "ADMIT",
            "QUARANTINE",
        }:
            raise ValueError(
                "INVALID_POINT_IN_TIME_DECISION_STATUS"
            )

        if (
            decision.downstream_eligible
            is not expected_eligible
        ):
            raise ValueError(
                "POINT_IN_TIME_ELIGIBILITY_MISMATCH"
            )

        expected_fingerprint = (
            compute_point_in_time_admission_decision_fingerprint(
                sport=decision.sport,
                canonical_id=decision.canonical_id,
                decision_status=decision.decision_status,
                downstream_eligible=(
                    decision.downstream_eligible
                ),
                as_of=decision.as_of,
                record_fingerprint=(
                    decision.record_fingerprint
                ),
                mapping_fingerprint=(
                    decision.mapping_fingerprint
                ),
                reason_codes=decision.reason_codes,
            )
        )

        if (
            expected_fingerprint
            != decision.decision_fingerprint
        ):
            raise ValueError(
                "POINT_IN_TIME_DECISION_DERIVATION_MISMATCH"
            )

    @staticmethod
    def evidence_id_for(
        decision: PointInTimeAdmissionDecision,
    ) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.point-in-time-admission-evidence-id/1"
                ),
                "sport": decision.sport,
                "canonical_id": decision.canonical_id,
                "record_fingerprint": (
                    decision.record_fingerprint
                ),
                "decision_fingerprint": (
                    decision.decision_fingerprint
                ),
                "decision_status": decision.decision_status,
                "downstream_eligible": (
                    decision.downstream_eligible
                ),
            }
        )

    def record_decision(
        self,
        decision: PointInTimeAdmissionDecision,
    ) -> PointInTimeAdmissionEvidence:
        self._validate_decision(decision)

        payload = {
            "schema": (
                "matrix.point-in-time-admission-evidence/1"
            ),
            "sport": decision.sport,
            "canonical_id": decision.canonical_id,
            "decision_status": decision.decision_status,
            "downstream_eligible": (
                decision.downstream_eligible
            ),
            "as_of": _iso(decision.as_of),
            "record_fingerprint": (
                decision.record_fingerprint
            ),
            "mapping_fingerprint": (
                decision.mapping_fingerprint
            ),
            "reason_codes": list(decision.reason_codes),
            "decision_fingerprint": (
                decision.decision_fingerprint
            ),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        payload_json = _canonical_json(payload)
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        evidence_id = self.evidence_id_for(decision)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT evidence_id, payload_sha256
                FROM point_in_time_admission_evidence
                WHERE decision_fingerprint = ?
                """,
                (decision.decision_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return PointInTimeAdmissionEvidence(
                        evidence_id=evidence_id,
                        sport=decision.sport,
                        canonical_id=decision.canonical_id,
                        decision_status=(
                            decision.decision_status
                        ),
                        downstream_eligible=(
                            decision.downstream_eligible
                        ),
                        record_fingerprint=(
                            decision.record_fingerprint
                        ),
                        decision_fingerprint=(
                            decision.decision_fingerprint
                        ),
                    )

                raise ValueError(
                    "POINT_IN_TIME_ADMISSION_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO point_in_time_admission_evidence (
                        evidence_id,
                        sport,
                        canonical_id,
                        record_fingerprint,
                        decision_fingerprint,
                        decision_status,
                        downstream_eligible,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        decision.sport,
                        decision.canonical_id,
                        decision.record_fingerprint,
                        decision.decision_fingerprint,
                        decision.decision_status,
                        int(decision.downstream_eligible),
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "POINT_IN_TIME_ADMISSION_APPEND_ONLY_VIOLATION"
                ) from error

        return PointInTimeAdmissionEvidence(
            evidence_id=evidence_id,
            sport=decision.sport,
            canonical_id=decision.canonical_id,
            decision_status=decision.decision_status,
            downstream_eligible=decision.downstream_eligible,
            record_fingerprint=decision.record_fingerprint,
            decision_fingerprint=decision.decision_fingerprint,
        )

    def get_by_decision_fingerprint(
        self,
        decision_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        if (
            not isinstance(decision_fingerprint, str)
            or len(decision_fingerprint) != 64
        ):
            raise ValueError(
                "INVALID_DECISION_FINGERPRINT"
            )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM point_in_time_admission_evidence
                WHERE decision_fingerprint = ?
                """,
                (decision_fingerprint,),
            ).fetchone()

        return None if row is None else json.loads(row[0])

    def audit_integrity(
        self,
    ) -> PointInTimeAdmissionEvidenceIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    canonical_id,
                    record_fingerprint,
                    decision_fingerprint,
                    decision_status,
                    downstream_eligible,
                    payload_json,
                    payload_sha256
                FROM point_in_time_admission_evidence
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for row in rows:
            (
                evidence_id,
                sport,
                canonical_id,
                record_fingerprint,
                decision_fingerprint,
                decision_status,
                downstream_eligible,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{decision_fingerprint}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{decision_fingerprint}"
                )

            expected_pairs = {
                "sport": sport,
                "canonical_id": canonical_id,
                "record_fingerprint": (
                    record_fingerprint
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
                "decision_status": decision_status,
                "downstream_eligible": bool(
                    downstream_eligible
                ),
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{decision_fingerprint}"
                    )

            expected_evidence_id = _sha(
                {
                    "schema": (
                        "matrix.point-in-time-admission-evidence-id/1"
                    ),
                    "sport": sport,
                    "canonical_id": canonical_id,
                    "record_fingerprint": (
                        record_fingerprint
                    ),
                    "decision_fingerprint": (
                        decision_fingerprint
                    ),
                    "decision_status": decision_status,
                    "downstream_eligible": bool(
                        downstream_eligible
                    ),
                }
            )

            if evidence_id != expected_evidence_id:
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:{decision_fingerprint}"
                )

            expected_eligible = (
                decision_status == "ADMIT"
            )
            if (
                bool(downstream_eligible)
                != expected_eligible
            ):
                errors.append(
                    f"STATUS_ELIGIBILITY_MISMATCH:"
                    f"{decision_fingerprint}"
                )

            if (
                payload.get("automatic_provider_switch")
                is not False
            ):
                errors.append(
                    f"AUTO_SWITCH_ENABLED:"
                    f"{decision_fingerprint}"
                )

            if payload.get("automatic_wagering") is not False:
                errors.append(
                    f"AUTO_WAGERING_ENABLED:"
                    f"{decision_fingerprint}"
                )

        return PointInTimeAdmissionEvidenceIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
