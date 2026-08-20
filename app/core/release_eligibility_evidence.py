from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.quality_gate_evidence import (
    SQLiteQualityGatePassEvidenceStore,
)


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
class ReleaseEligibilityDecision:
    commit_sha: str
    policy_fingerprint: str
    dependency_inventory_fingerprint: str
    quality_gate_evidence_id: str
    status: str
    decision_fingerprint: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.release-eligibility-decision/3"
            ),
            "commit_sha": self.commit_sha,
            "policy_fingerprint": (
                self.policy_fingerprint
            ),
            "dependency_inventory_fingerprint": (
                self.dependency_inventory_fingerprint
            ),
            "quality_gate_evidence_id": (
                self.quality_gate_evidence_id
            ),
            "verified_quality_gate_required": True,
            "status": self.status,
            "automatic_deploy": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "decision_fingerprint": (
                self.decision_fingerprint
            ),
        }


@dataclass(frozen=True)
class ReleaseEligibilityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


def build_release_eligibility_from_verified_gate(
    *,
    gate_store: SQLiteQualityGatePassEvidenceStore,
    quality_gate_evidence_id: str,
    expected_commit_sha: str,
    expected_policy_fingerprint: str,
    expected_dependency_inventory_fingerprint: str,
) -> ReleaseEligibilityDecision:
    quality_gate_evidence_id = _hex(
        "QUALITY_GATE_EVIDENCE_ID",
        quality_gate_evidence_id,
        {64},
    )
    expected_commit_sha = _hex(
        "COMMIT_SHA",
        expected_commit_sha,
        {40, 64},
    )
    expected_policy_fingerprint = _hex(
        "POLICY_FINGERPRINT",
        expected_policy_fingerprint,
        {64},
    )
    expected_dependency_inventory_fingerprint = _hex(
        "DEPENDENCY_INVENTORY_FINGERPRINT",
        expected_dependency_inventory_fingerprint,
        {64},
    )

    evidence = gate_store.get_verified(
        quality_gate_evidence_id
    )

    reasons: list[str] = []

    if evidence is None:
        reasons.append(
            "MISSING_VERIFIED_QUALITY_GATE_EVIDENCE"
        )
    else:
        if evidence.status != "PASS":
            reasons.append(
                "QUALITY_GATE_NOT_PASS"
            )

        if (
            evidence.commit_sha
            != expected_commit_sha
        ):
            reasons.append(
                "QUALITY_GATE_COMMIT_MISMATCH"
            )

        if (
            evidence.policy_fingerprint
            != expected_policy_fingerprint
        ):
            reasons.append(
                "QUALITY_GATE_POLICY_MISMATCH"
            )

        if (
            evidence
            .dependency_inventory_fingerprint
            != expected_dependency_inventory_fingerprint
        ):
            reasons.append(
                "QUALITY_GATE_DEPENDENCY_INVENTORY_MISMATCH"
            )

    status = (
        "ELIGIBLE_FOR_MANUAL_RELEASE"
        if not reasons
        else "QUARANTINE"
    )

    base = {
        "schema": (
            "matrix.release-eligibility-decision/3"
        ),
        "commit_sha": expected_commit_sha,
        "policy_fingerprint": (
            expected_policy_fingerprint
        ),
        "dependency_inventory_fingerprint": (
            expected_dependency_inventory_fingerprint
        ),
        "quality_gate_evidence_id": (
            quality_gate_evidence_id
        ),
        "verified_quality_gate_required": True,
        "status": status,
        "automatic_deploy": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return ReleaseEligibilityDecision(
        commit_sha=expected_commit_sha,
        policy_fingerprint=(
            expected_policy_fingerprint
        ),
        dependency_inventory_fingerprint=(
            expected_dependency_inventory_fingerprint
        ),
        quality_gate_evidence_id=(
            quality_gate_evidence_id
        ),
        status=status,
        decision_fingerprint=_sha(
            base
        ),
    )


class SQLiteReleaseEligibilityEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS release_eligibility_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    commit_sha TEXT NOT NULL UNIQUE,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
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
                    "matrix.release-eligibility-evidence-id/3"
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
            }
        )

    @staticmethod
    def _rederive(
        payload: Mapping[str, Any],
    ) -> str:
        base = {
            "schema": (
                "matrix.release-eligibility-decision/3"
            ),
            "commit_sha": payload[
                "commit_sha"
            ],
            "policy_fingerprint": payload[
                "policy_fingerprint"
            ],
            "dependency_inventory_fingerprint": payload[
                "dependency_inventory_fingerprint"
            ],
            "quality_gate_evidence_id": payload[
                "quality_gate_evidence_id"
            ],
            "verified_quality_gate_required": True,
            "status": payload[
                "status"
            ],
            "automatic_deploy": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }

        return _sha(
            base
        )

    def record(
        self,
        decision: ReleaseEligibilityDecision,
    ) -> str:
        payload = dict(
            decision.payload()
        )

        if (
            self._rederive(
                payload
            )
            != decision.decision_fingerprint
        ):
            raise ValueError(
                "RELEASE_ELIGIBILITY_DERIVATION_MISMATCH"
            )

        evidence_id = self._evidence_id(
            decision.decision_fingerprint
        )
        payload["evidence_id"] = (
            evidence_id
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
                FROM release_eligibility_evidence
                WHERE commit_sha = ?
                """,
                (
                    decision.commit_sha,
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
                    "RELEASE_ELIGIBILITY_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO release_eligibility_evidence (
                    evidence_id,
                    commit_sha,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    decision.commit_sha,
                    decision.decision_fingerprint,
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
    ) -> ReleaseEligibilityIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    commit_sha,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM release_eligibility_evidence
                ORDER BY evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            commit_sha,
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
                    f"INVALID_JSON:{commit_sha}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(
                    payload
                ).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{commit_sha}"
                )

            try:
                expected_fp = self._rederive(
                    payload
                )
            except Exception:
                errors.append(
                    f"REDERIVATION_FAILED:{commit_sha}"
                )
                continue

            if expected_fp != decision_fp:
                errors.append(
                    "DECISION_FINGERPRINT_MISMATCH:"
                    f"{commit_sha}"
                )

            if (
                self._evidence_id(
                    decision_fp
                )
                != evidence_id
            ):
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:{commit_sha}"
                )

        return ReleaseEligibilityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
