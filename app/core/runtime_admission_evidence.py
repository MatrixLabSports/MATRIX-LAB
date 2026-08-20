from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.runtime_admission_gate import RuntimeAdmissionDecision


_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_STATUSES = {"ADMIT", "QUARANTINE"}


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
class RuntimeAdmissionEvidence:
    evidence_id: str
    run_id: str
    sport: str
    admission_status: str
    downstream_eligible: bool
    decision_fingerprint: str
    reconciliation_fingerprint: str


@dataclass(frozen=True)
class RuntimeAdmissionEvidenceIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteRuntimeAdmissionEvidenceLedger:
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
                CREATE TABLE IF NOT EXISTS runtime_admission_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    admission_status TEXT NOT NULL,
                    downstream_eligible INTEGER NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    reconciliation_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (admission_status IN ('ADMIT', 'QUARANTINE')),
                    CHECK (downstream_eligible IN (0, 1))
                )
                """
            )

    @staticmethod
    def evidence_id_for(
        decision: RuntimeAdmissionDecision,
    ) -> str:
        payload = {
            "schema": "matrix.runtime-admission-evidence-id/1",
            "run_id": decision.run_id,
            "sport": decision.sport,
            "admission_status": decision.admission_status,
            "downstream_eligible": decision.downstream_eligible,
            "decision_fingerprint": decision.decision_fingerprint,
            "reconciliation_fingerprint": decision.reconciliation_fingerprint,
        }
        return _sha256_text(_canonical_json(payload))

    def record_decision(
        self,
        decision: RuntimeAdmissionDecision,
    ) -> RuntimeAdmissionEvidence:
        run_id = _validate_hex64("RUN_ID", decision.run_id)
        decision_fp = _validate_hex64(
            "DECISION_FINGERPRINT",
            decision.decision_fingerprint,
        )
        reconciliation_fp = _validate_hex64(
            "RECONCILIATION_FINGERPRINT",
            decision.reconciliation_fingerprint,
        )

        if decision.sport not in _ALLOWED_SPORTS:
            raise ValueError("INVALID_SPORT")

        if decision.admission_status not in _ALLOWED_STATUSES:
            raise ValueError("INVALID_ADMISSION_STATUS")

        expected_eligible = decision.admission_status == "ADMIT"
        if decision.downstream_eligible is not expected_eligible:
            raise ValueError("ADMISSION_ELIGIBILITY_MISMATCH")

        payload = dict(decision.payload())
        payload_json = _canonical_json(payload)
        payload_sha = _sha256_text(payload_json)
        evidence_id = self.evidence_id_for(decision)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    decision_fingerprint,
                    payload_sha256
                FROM runtime_admission_evidence
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == decision_fp
                    and str(existing[2]) == payload_sha
                ):
                    return RuntimeAdmissionEvidence(
                        evidence_id=evidence_id,
                        run_id=run_id,
                        sport=decision.sport,
                        admission_status=decision.admission_status,
                        downstream_eligible=decision.downstream_eligible,
                        decision_fingerprint=decision_fp,
                        reconciliation_fingerprint=reconciliation_fp,
                    )

                raise ValueError("RUNTIME_ADMISSION_MUTATION_VIOLATION")

            try:
                connection.execute(
                    """
                    INSERT INTO runtime_admission_evidence (
                        evidence_id,
                        run_id,
                        sport,
                        admission_status,
                        downstream_eligible,
                        decision_fingerprint,
                        reconciliation_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        run_id,
                        decision.sport,
                        decision.admission_status,
                        int(decision.downstream_eligible),
                        decision_fp,
                        reconciliation_fp,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "RUNTIME_ADMISSION_APPEND_ONLY_VIOLATION"
                ) from error

        return RuntimeAdmissionEvidence(
            evidence_id=evidence_id,
            run_id=run_id,
            sport=decision.sport,
            admission_status=decision.admission_status,
            downstream_eligible=decision.downstream_eligible,
            decision_fingerprint=decision_fp,
            reconciliation_fingerprint=reconciliation_fp,
        )

    def get_by_run_id(
        self,
        run_id: str,
    ) -> Mapping[str, Any] | None:
        validated_run = _validate_hex64("RUN_ID", run_id)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM runtime_admission_evidence
                WHERE run_id = ?
                """,
                (validated_run,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def audit_integrity(
        self,
    ) -> RuntimeAdmissionEvidenceIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    run_id,
                    sport,
                    admission_status,
                    downstream_eligible,
                    decision_fingerprint,
                    reconciliation_fingerprint,
                    payload_json,
                    payload_sha256
                FROM runtime_admission_evidence
                ORDER BY run_id
                """
            ).fetchall()

        for (
            evidence_id,
            run_id,
            sport,
            admission_status,
            downstream_eligible,
            decision_fp,
            reconciliation_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{run_id}")
                continue

            canonical = _canonical_json(payload)
            actual_sha = _sha256_text(canonical)

            if actual_sha != stored_sha:
                errors.append(f"PAYLOAD_HASH_MISMATCH:{run_id}")

            if payload.get("run_id") != run_id:
                errors.append(f"RUN_ID_MISMATCH:{run_id}")

            if payload.get("sport") != sport:
                errors.append(f"SPORT_MISMATCH:{run_id}")

            if payload.get("admission_status") != admission_status:
                errors.append(f"STATUS_MISMATCH:{run_id}")

            if bool(payload.get("downstream_eligible")) != bool(
                downstream_eligible
            ):
                errors.append(f"ELIGIBILITY_MISMATCH:{run_id}")

            if payload.get("decision_fingerprint") != decision_fp:
                errors.append(f"DECISION_FINGERPRINT_MISMATCH:{run_id}")

            if (
                payload.get("reconciliation_fingerprint")
                != reconciliation_fp
            ):
                errors.append(
                    f"RECONCILIATION_FINGERPRINT_MISMATCH:{run_id}"
                )

            expected_evidence = _sha256_text(
                _canonical_json(
                    {
                        "schema": "matrix.runtime-admission-evidence-id/1",
                        "run_id": run_id,
                        "sport": sport,
                        "admission_status": admission_status,
                        "downstream_eligible": bool(downstream_eligible),
                        "decision_fingerprint": decision_fp,
                        "reconciliation_fingerprint": reconciliation_fp,
                    }
                )
            )

            if evidence_id != expected_evidence:
                errors.append(f"EVIDENCE_ID_MISMATCH:{run_id}")

            if (
                admission_status == "ADMIT"
                and not bool(downstream_eligible)
            ):
                errors.append(f"ADMIT_NOT_ELIGIBLE:{run_id}")

            if (
                admission_status == "QUARANTINE"
                and bool(downstream_eligible)
            ):
                errors.append(f"QUARANTINE_ELIGIBLE:{run_id}")

        return RuntimeAdmissionEvidenceIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
