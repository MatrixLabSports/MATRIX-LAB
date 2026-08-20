from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.provider_health_policy import ProviderHealthDecision


_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_STATUSES = {"ELIGIBLE", "REVIEW_REQUIRED", "INELIGIBLE"}


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
class ProviderHealthEvidence:
    evidence_id: str
    provider_key: str
    sport: str
    decision_status: str
    scheduling_eligible: bool
    snapshot_fingerprint: str
    policy_fingerprint: str
    decision_fingerprint: str


@dataclass(frozen=True)
class ProviderHealthEvidenceIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderHealthEvidenceLedger:
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
                CREATE TABLE IF NOT EXISTS provider_health_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    provider_key TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    decision_status TEXT NOT NULL,
                    scheduling_eligible INTEGER NOT NULL,
                    snapshot_fingerprint TEXT NOT NULL,
                    policy_fingerprint TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE (
                        provider_key,
                        sport,
                        snapshot_fingerprint,
                        policy_fingerprint
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (
                        decision_status IN (
                            'ELIGIBLE',
                            'REVIEW_REQUIRED',
                            'INELIGIBLE'
                        )
                    ),
                    CHECK (scheduling_eligible IN (0, 1))
                )
                """
            )

    @staticmethod
    def evidence_id_for(
        decision: ProviderHealthDecision,
    ) -> str:
        payload = {
            "schema": "matrix.provider-health-evidence-id/1",
            "provider_key": decision.provider_key,
            "sport": decision.sport,
            "decision_status": decision.decision_status,
            "scheduling_eligible": decision.scheduling_eligible,
            "snapshot_fingerprint": decision.snapshot_fingerprint,
            "policy_fingerprint": decision.policy_fingerprint,
            "decision_fingerprint": decision.decision_fingerprint,
        }
        return _sha256_text(_canonical_json(payload))

    def record_decision(
        self,
        decision: ProviderHealthDecision,
    ) -> ProviderHealthEvidence:
        if (
            not isinstance(decision.provider_key, str)
            or not decision.provider_key.strip()
        ):
            raise ValueError("INVALID_PROVIDER_KEY")

        if decision.sport not in _ALLOWED_SPORTS:
            raise ValueError("INVALID_SPORT")

        if decision.decision_status not in _ALLOWED_STATUSES:
            raise ValueError("INVALID_DECISION_STATUS")

        expected_eligible = decision.decision_status == "ELIGIBLE"
        if decision.scheduling_eligible is not expected_eligible:
            raise ValueError("HEALTH_ELIGIBILITY_MISMATCH")

        snapshot_fp = _validate_hex64(
            "SNAPSHOT_FINGERPRINT",
            decision.snapshot_fingerprint,
        )
        policy_fp = _validate_hex64(
            "POLICY_FINGERPRINT",
            decision.policy_fingerprint,
        )
        decision_fp = _validate_hex64(
            "DECISION_FINGERPRINT",
            decision.decision_fingerprint,
        )

        payload = dict(decision.payload())
        payload_json = _canonical_json(payload)
        payload_sha = _sha256_text(payload_json)
        evidence_id = self.evidence_id_for(decision)

        key = (
            decision.provider_key,
            decision.sport,
            snapshot_fp,
            policy_fp,
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    decision_fingerprint,
                    payload_sha256
                FROM provider_health_evidence
                WHERE
                    provider_key = ?
                    AND sport = ?
                    AND snapshot_fingerprint = ?
                    AND policy_fingerprint = ?
                """,
                key,
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == decision_fp
                    and str(existing[2]) == payload_sha
                ):
                    return ProviderHealthEvidence(
                        evidence_id=evidence_id,
                        provider_key=decision.provider_key,
                        sport=decision.sport,
                        decision_status=decision.decision_status,
                        scheduling_eligible=decision.scheduling_eligible,
                        snapshot_fingerprint=snapshot_fp,
                        policy_fingerprint=policy_fp,
                        decision_fingerprint=decision_fp,
                    )

                raise ValueError("PROVIDER_HEALTH_MUTATION_VIOLATION")

            try:
                connection.execute(
                    """
                    INSERT INTO provider_health_evidence (
                        evidence_id,
                        provider_key,
                        sport,
                        decision_status,
                        scheduling_eligible,
                        snapshot_fingerprint,
                        policy_fingerprint,
                        decision_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        decision.provider_key,
                        decision.sport,
                        decision.decision_status,
                        int(decision.scheduling_eligible),
                        snapshot_fp,
                        policy_fp,
                        decision_fp,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "PROVIDER_HEALTH_APPEND_ONLY_VIOLATION"
                ) from error

        return ProviderHealthEvidence(
            evidence_id=evidence_id,
            provider_key=decision.provider_key,
            sport=decision.sport,
            decision_status=decision.decision_status,
            scheduling_eligible=decision.scheduling_eligible,
            snapshot_fingerprint=snapshot_fp,
            policy_fingerprint=policy_fp,
            decision_fingerprint=decision_fp,
        )

    def get_by_decision_fingerprint(
        self,
        decision_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        validated = _validate_hex64(
            "DECISION_FINGERPRINT",
            decision_fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM provider_health_evidence
                WHERE decision_fingerprint = ?
                """,
                (validated,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def audit_integrity(
        self,
    ) -> ProviderHealthEvidenceIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    provider_key,
                    sport,
                    decision_status,
                    scheduling_eligible,
                    snapshot_fingerprint,
                    policy_fingerprint,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM provider_health_evidence
                ORDER BY provider_key, sport, created_at, evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            provider_key,
            sport,
            decision_status,
            scheduling_eligible,
            snapshot_fp,
            policy_fp,
            decision_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{provider_key}:{sport}"
                )
                continue

            canonical = _canonical_json(payload)
            actual_sha = _sha256_text(canonical)

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{provider_key}:{sport}"
                )

            expected_pairs = {
                "provider_key": provider_key,
                "sport": sport,
                "decision_status": decision_status,
                "scheduling_eligible": bool(scheduling_eligible),
                "snapshot_fingerprint": snapshot_fp,
                "policy_fingerprint": policy_fp,
                "decision_fingerprint": decision_fp,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:{provider_key}:{sport}"
                    )

            expected_evidence = _sha256_text(
                _canonical_json(
                    {
                        "schema": "matrix.provider-health-evidence-id/1",
                        "provider_key": provider_key,
                        "sport": sport,
                        "decision_status": decision_status,
                        "scheduling_eligible": bool(
                            scheduling_eligible
                        ),
                        "snapshot_fingerprint": snapshot_fp,
                        "policy_fingerprint": policy_fp,
                        "decision_fingerprint": decision_fp,
                    }
                )
            )

            if evidence_id != expected_evidence:
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:{provider_key}:{sport}"
                )

            if (
                decision_status == "ELIGIBLE"
                and not bool(scheduling_eligible)
            ):
                errors.append(
                    f"ELIGIBLE_NOT_SCHEDULABLE:{provider_key}:{sport}"
                )

            if (
                decision_status != "ELIGIBLE"
                and bool(scheduling_eligible)
            ):
                errors.append(
                    f"NON_ELIGIBLE_SCHEDULABLE:{provider_key}:{sport}"
                )

            if payload.get("automatic_provider_switch") is not False:
                errors.append(
                    f"AUTO_SWITCH_ENABLED:{provider_key}:{sport}"
                )

        return ProviderHealthEvidenceIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
