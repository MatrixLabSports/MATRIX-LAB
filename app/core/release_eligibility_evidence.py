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
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _hex40_or_64(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in {40, 64}
    ):
        raise ValueError(f"INVALID_{name}")

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
    canonical_tests_passed: bool
    static_checks_passed: bool
    security_scan_passed: bool
    status: str
    decision_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.release-eligibility-decision/2"
            ),
            "commit_sha": self.commit_sha,
            "policy_fingerprint": (
                self.policy_fingerprint
            ),
            "dependency_inventory_fingerprint": (
                self.dependency_inventory_fingerprint
            ),
            "canonical_tests_passed": (
                self.canonical_tests_passed
            ),
            "static_checks_passed": (
                self.static_checks_passed
            ),
            "security_scan_passed": (
                self.security_scan_passed
            ),
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


def build_release_eligibility_decision(
    *,
    commit_sha: str,
    policy_fingerprint: str,
    dependency_inventory_fingerprint: str,
    canonical_tests_passed: bool,
    static_checks_passed: bool,
    security_scan_passed: bool,
) -> ReleaseEligibilityDecision:
    commit_sha = _hex40_or_64(
        "COMMIT_SHA",
        commit_sha,
    )
    policy_fingerprint = _hex40_or_64(
        "POLICY_FINGERPRINT",
        policy_fingerprint,
    )
    dependency_inventory_fingerprint = (
        _hex40_or_64(
            "DEPENDENCY_INVENTORY_FINGERPRINT",
            dependency_inventory_fingerprint,
        )
    )

    flags = (
        canonical_tests_passed,
        static_checks_passed,
        security_scan_passed,
    )

    if any(
        not isinstance(value, bool)
        for value in flags
    ):
        raise ValueError(
            "INVALID_RELEASE_GATE_BOOLEAN"
        )

    status = (
        "ELIGIBLE_FOR_MANUAL_RELEASE"
        if all(flags)
        else "QUARANTINE"
    )

    base = {
        "schema": (
            "matrix.release-eligibility-decision/2"
        ),
        "commit_sha": commit_sha,
        "policy_fingerprint": (
            policy_fingerprint
        ),
        "dependency_inventory_fingerprint": (
            dependency_inventory_fingerprint
        ),
        "canonical_tests_passed": (
            canonical_tests_passed
        ),
        "static_checks_passed": (
            static_checks_passed
        ),
        "security_scan_passed": (
            security_scan_passed
        ),
        "status": status,
        "automatic_deploy": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return ReleaseEligibilityDecision(
        commit_sha=commit_sha,
        policy_fingerprint=policy_fingerprint,
        dependency_inventory_fingerprint=(
            dependency_inventory_fingerprint
        ),
        canonical_tests_passed=(
            canonical_tests_passed
        ),
        static_checks_passed=(
            static_checks_passed
        ),
        security_scan_passed=(
            security_scan_passed
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
                    "matrix.release-eligibility-evidence-id/2"
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
            }
        )

    @staticmethod
    def _rederive(
        payload: Mapping[str, Any],
    ) -> ReleaseEligibilityDecision:
        return build_release_eligibility_decision(
            commit_sha=payload[
                "commit_sha"
            ],
            policy_fingerprint=payload[
                "policy_fingerprint"
            ],
            dependency_inventory_fingerprint=payload[
                "dependency_inventory_fingerprint"
            ],
            canonical_tests_passed=payload[
                "canonical_tests_passed"
            ],
            static_checks_passed=payload[
                "static_checks_passed"
            ],
            security_scan_passed=payload[
                "security_scan_passed"
            ],
        )

    def record(
        self,
        decision: ReleaseEligibilityDecision,
    ) -> str:
        expected = (
            build_release_eligibility_decision(
                commit_sha=decision.commit_sha,
                policy_fingerprint=(
                    decision.policy_fingerprint
                ),
                dependency_inventory_fingerprint=(
                    decision
                    .dependency_inventory_fingerprint
                ),
                canonical_tests_passed=(
                    decision
                    .canonical_tests_passed
                ),
                static_checks_passed=(
                    decision.static_checks_passed
                ),
                security_scan_passed=(
                    decision
                    .security_scan_passed
                ),
            )
        )

        if expected != decision:
            raise ValueError(
                "RELEASE_ELIGIBILITY_DERIVATION_MISMATCH"
            )

        evidence_id = self._evidence_id(
            decision.decision_fingerprint
        )

        payload = dict(
            decision.payload()
        )
        payload["evidence_id"] = evidence_id

        payload_json = _canonical_json(
            payload
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
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
                expected = self._rederive(
                    payload
                )
            except Exception:
                errors.append(
                    f"REDERIVATION_FAILED:{commit_sha}"
                )
                continue

            if (
                expected.decision_fingerprint
                != decision_fp
            ):
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

            for key, expected_value in {
                "evidence_id": evidence_id,
                "commit_sha": commit_sha,
                "decision_fingerprint": (
                    decision_fp
                ),
                "automatic_deploy": False,
                "automatic_model_promotion": False,
                "automatic_wagering": False,
            }.items():
                if (
                    payload.get(key)
                    != expected_value
                ):
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{commit_sha}"
                    )

        return ReleaseEligibilityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
