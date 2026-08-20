from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _hex(
    name: str,
    value: object,
    lengths: set[int],
) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in lengths
    ):
        raise ValueError(
            f"INVALID_{name}"
        )

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error

    return value.lower()


@dataclass(frozen=True)
class QualityGatePassEvidence:
    commit_sha: str
    policy_fingerprint: str
    dependency_inventory_fingerprint: str
    status: str
    evidence_id: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.quality-gate-pass-evidence/1"
            ),
            "commit_sha": self.commit_sha,
            "policy_fingerprint": (
                self.policy_fingerprint
            ),
            "dependency_inventory_fingerprint": (
                self.dependency_inventory_fingerprint
            ),
            "status": self.status,
            "canonical_tests_passed": True,
            "static_checks_passed": True,
            "security_scan_passed": True,
            "automatic_deploy": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "evidence_id": self.evidence_id,
        }


class SQLiteQualityGatePassEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS quality_gate_pass_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    commit_sha TEXT NOT NULL UNIQUE,
                    policy_fingerprint TEXT NOT NULL,
                    dependency_inventory_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def build(
        *,
        commit_sha: str,
        policy_fingerprint: str,
        dependency_inventory_fingerprint: str,
    ) -> QualityGatePassEvidence:
        commit_sha = _hex(
            "COMMIT_SHA",
            commit_sha,
            {40, 64},
        )
        policy_fingerprint = _hex(
            "POLICY_FINGERPRINT",
            policy_fingerprint,
            {64},
        )
        dependency_inventory_fingerprint = _hex(
            "DEPENDENCY_INVENTORY_FINGERPRINT",
            dependency_inventory_fingerprint,
            {64},
        )

        base = {
            "schema": (
                "matrix.quality-gate-pass-evidence-id/1"
            ),
            "commit_sha": commit_sha,
            "policy_fingerprint": (
                policy_fingerprint
            ),
            "dependency_inventory_fingerprint": (
                dependency_inventory_fingerprint
            ),
            "status": "PASS",
            "canonical_tests_passed": True,
            "static_checks_passed": True,
            "security_scan_passed": True,
            "automatic_deploy": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }

        return QualityGatePassEvidence(
            commit_sha=commit_sha,
            policy_fingerprint=(
                policy_fingerprint
            ),
            dependency_inventory_fingerprint=(
                dependency_inventory_fingerprint
            ),
            status="PASS",
            evidence_id=_sha(
                base
            ),
        )

    def record(
        self,
        evidence: QualityGatePassEvidence,
    ) -> str:
        expected = self.build(
            commit_sha=evidence.commit_sha,
            policy_fingerprint=(
                evidence.policy_fingerprint
            ),
            dependency_inventory_fingerprint=(
                evidence
                .dependency_inventory_fingerprint
            ),
        )

        if expected != evidence:
            raise ValueError(
                "QUALITY_GATE_EVIDENCE_DERIVATION_MISMATCH"
            )

        payload = dict(
            evidence.payload()
        )
        payload_json = (
            _canonical_json(
                payload
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
                FROM quality_gate_pass_evidence
                WHERE commit_sha = ?
                """,
                (
                    evidence.commit_sha,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == evidence.evidence_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return evidence.evidence_id

                raise ValueError(
                    "QUALITY_GATE_EVIDENCE_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO quality_gate_pass_evidence (
                    evidence_id,
                    commit_sha,
                    policy_fingerprint,
                    dependency_inventory_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.commit_sha,
                    evidence.policy_fingerprint,
                    evidence
                    .dependency_inventory_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return evidence.evidence_id

    def get_verified(
        self,
        evidence_id: str,
    ) -> QualityGatePassEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    commit_sha,
                    policy_fingerprint,
                    dependency_inventory_fingerprint,
                    payload_json,
                    payload_sha256
                FROM quality_gate_pass_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

        if row is None:
            return None

        (
            commit_sha,
            policy_fp,
            dependency_fp,
            payload_json,
            stored_sha,
        ) = row

        payload = json.loads(
            payload_json
        )

        actual_sha = sha256(
            _canonical_json(
                payload
            ).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError(
                "QUALITY_GATE_EVIDENCE_HASH_MISMATCH"
            )

        expected = self.build(
            commit_sha=commit_sha,
            policy_fingerprint=policy_fp,
            dependency_inventory_fingerprint=(
                dependency_fp
            ),
        )

        if (
            expected.evidence_id
            != evidence_id
            or payload
            != expected.payload()
        ):
            raise ValueError(
                "QUALITY_GATE_EVIDENCE_REDERIVATION_MISMATCH"
            )

        return expected
