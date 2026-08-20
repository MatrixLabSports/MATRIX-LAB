from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.provider_security_gate import (
    ProviderSecurityDecision,
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


def _decision_fingerprint(
    payload: Mapping[str, Any],
) -> str:
    base = dict(payload)
    base.pop("evidence_id", None)
    base.pop("decision_fingerprint", None)

    return _sha(
        {
            "schema": (
                "matrix.provider-security-decision/1"
            ),
            "status": base["status"],
            "executable": base["executable"],
            "run_id": base["run_id"],
            "sport": base["sport"],
            "provider_key": (
                base["provider_key"]
            ),
            "mode": base["mode"],
            "preflight_decision_fingerprint": (
                base[
                    "preflight_decision_fingerprint"
                ]
            ),
            "endpoint_policy_fingerprint": (
                base[
                    "endpoint_policy_fingerprint"
                ]
            ),
            "secret_reference_fingerprint": (
                base[
                    "secret_reference_fingerprint"
                ]
            ),
            "reason_codes": sorted(
                base["reason_codes"]
            ),
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "certificate_verification_required": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
    )


@dataclass(frozen=True)
class ProviderSecurityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderSecurityEvidenceStore:
    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize()

    def _connect(
        self,
    ) -> sqlite3.Connection:
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
                CREATE TABLE IF NOT EXISTS provider_security_evidence (
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
                    "matrix.provider-security-evidence-id/1"
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
            }
        )

    def record(
        self,
        decision: ProviderSecurityDecision,
    ) -> str:
        payload = dict(
            decision.payload()
        )

        expected_fp = (
            _decision_fingerprint(
                payload
            )
        )

        if (
            expected_fp
            != decision
            .decision_fingerprint
        ):
            raise ValueError(
                "PROVIDER_SECURITY_DECISION_DERIVATION_MISMATCH"
            )

        if (
            decision.executable
            != (
                decision.status
                == "EXECUTE"
            )
        ):
            raise ValueError(
                "PROVIDER_SECURITY_STATUS_MISMATCH"
            )

        evidence_id = (
            self._evidence_id(
                decision
                .decision_fingerprint
            )
        )

        evidence_payload = dict(
            payload
        )
        evidence_payload[
            "evidence_id"
        ] = evidence_id

        payload_json = (
            _canonical_json(
                evidence_payload
            )
        )
        payload_sha = sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    payload_sha256
                FROM provider_security_evidence
                WHERE run_id = ?
                """,
                (
                    decision.run_id,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == evidence_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return evidence_id

                raise ValueError(
                    "PROVIDER_SECURITY_RUN_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO provider_security_evidence (
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
                    decision
                    .decision_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return evidence_id

    def audit_integrity(
        self,
    ) -> ProviderSecurityIntegrityReport:
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
                FROM provider_security_evidence
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
                payload = json.loads(
                    payload_json
                )
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{decision_fp}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(
                    payload
                ).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    "PAYLOAD_HASH_MISMATCH:"
                    f"{decision_fp}"
                )

            expected_fp = (
                _decision_fingerprint(
                    payload
                )
            )

            if (
                expected_fp
                != decision_fp
            ):
                errors.append(
                    "DECISION_FINGERPRINT_MISMATCH:"
                    f"{decision_fp}"
                )

            expected_evidence_id = (
                self._evidence_id(
                    decision_fp
                )
            )

            if (
                expected_evidence_id
                != evidence_id
            ):
                errors.append(
                    "EVIDENCE_ID_MISMATCH:"
                    f"{decision_fp}"
                )

            for key, expected in {
                "evidence_id": evidence_id,
                "run_id": run_id,
                "sport": sport,
                "provider_key": provider_key,
                "decision_fingerprint": (
                    decision_fp
                ),
                "raw_secret_persisted": False,
                "raw_secret_logged": False,
                "certificate_verification_required": True,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }.items():
                if (
                    payload.get(key)
                    != expected
                ):
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{decision_fp}"
                    )

        return ProviderSecurityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
