from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.provider_security_authorization import (
    AuthoritativeProviderSecurityDecision,
    _decision_fingerprint,
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


@dataclass(frozen=True)
class AuthoritativeProviderSecurityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteAuthoritativeProviderSecurityEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute(
            "PRAGMA journal_mode = WAL"
        )
        connection.execute(
            "PRAGMA synchronous = FULL"
        )
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS authoritative_provider_security_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    )
                )
                """
            )

    @staticmethod
    def _evidence_id(
        decision_fingerprint: str,
    ) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.authoritative-provider-security-evidence-id/1"
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
            }
        )

    @staticmethod
    def _rederive_from_payload(
        payload: Mapping[str, Any],
    ) -> str:
        return _decision_fingerprint(
            status=payload["status"],
            executable=payload["executable"],
            run_id=payload["run_id"],
            sport=payload["sport"],
            provider_key=payload["provider_key"],
            mode=payload["mode"],
            preflight_decision_fingerprint=(
                payload[
                    "preflight_decision_fingerprint"
                ]
            ),
            preflight_evidence_id=(
                payload["preflight_evidence_id"]
            ),
            baseline_security_decision_fingerprint=(
                payload[
                    "baseline_security_decision_fingerprint"
                ]
            ),
            endpoint_target_fingerprint=(
                payload[
                    "endpoint_target_fingerprint"
                ]
            ),
            secret_reference_fingerprint=(
                payload[
                    "secret_reference_fingerprint"
                ]
            ),
            secret_availability_attestation_fingerprint=(
                payload[
                    "secret_availability_attestation_fingerprint"
                ]
            ),
            reason_codes=payload["reason_codes"],
        )

    def record(
        self,
        decision: AuthoritativeProviderSecurityDecision,
    ) -> str:
        payload = dict(decision.payload())

        expected_fp = self._rederive_from_payload(
            payload
        )

        if expected_fp != decision.decision_fingerprint:
            raise ValueError(
                "AUTHORITATIVE_SECURITY_DECISION_DERIVATION_MISMATCH"
            )

        if (
            decision.executable
            != (decision.status == "EXECUTE")
        ):
            raise ValueError(
                "AUTHORITATIVE_SECURITY_STATUS_MISMATCH"
            )

        evidence_id = self._evidence_id(
            decision.decision_fingerprint
        )
        payload["evidence_id"] = evidence_id

        payload_json = _canonical_json(payload)
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    payload_sha256
                FROM authoritative_provider_security_evidence
                WHERE run_id = ?
                """,
                (decision.run_id,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return evidence_id
                raise ValueError(
                    "AUTHORITATIVE_SECURITY_RUN_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO authoritative_provider_security_evidence (
                    evidence_id,
                    run_id,
                    sport,
                    provider_key,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    decision.run_id,
                    decision.sport,
                    decision.provider_key,
                    decision.decision_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return evidence_id

    def audit_integrity(
        self,
    ) -> AuthoritativeProviderSecurityIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    run_id,
                    sport,
                    provider_key,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM authoritative_provider_security_evidence
                ORDER BY evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            run_id,
            sport,
            provider_key,
            decision_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{decision_fp}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    "PAYLOAD_HASH_MISMATCH:"
                    f"{decision_fp}"
                )

            try:
                expected_fp = (
                    self._rederive_from_payload(
                        payload
                    )
                )
            except Exception:
                errors.append(
                    "DECISION_REDERIVATION_FAILED:"
                    f"{decision_fp}"
                )
                continue

            if expected_fp != decision_fp:
                errors.append(
                    "DECISION_FINGERPRINT_MISMATCH:"
                    f"{decision_fp}"
                )

            expected_evidence_id = self._evidence_id(
                decision_fp
            )

            if expected_evidence_id != evidence_id:
                errors.append(
                    "EVIDENCE_ID_MISMATCH:"
                    f"{decision_fp}"
                )

            for key, expected in {
                "evidence_id": evidence_id,
                "run_id": run_id,
                "sport": sport,
                "provider_key": provider_key,
                "decision_fingerprint": decision_fp,
                "raw_secret_persisted": False,
                "raw_secret_logged": False,
                "secret_value_fingerprinted": False,
                "certificate_verification_required": True,
                "authoritative_for_future_provider_calls": True,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{decision_fp}"
                    )

        return AuthoritativeProviderSecurityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
