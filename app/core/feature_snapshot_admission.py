from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.canonical_observation_store import (
    SQLiteCanonicalObservationStore,
)
from app.core.feature_definition_registry import (
    SQLiteFeatureDefinitionRegistry,
)
from app.core.feature_snapshot_store import (
    SQLiteFeatureSnapshotStore,
)
from app.core.point_in_time_feature_snapshot import (
    build_point_in_time_feature_snapshot,
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


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("INVALID_AS_OF")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class FeatureSnapshotAdmissionDecision:
    sport: str
    snapshot_fingerprint: str
    decision_status: str
    downstream_eligible: bool
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


@dataclass(frozen=True)
class FeatureSnapshotAdmissionEvidence:
    evidence_id: str
    sport: str
    snapshot_fingerprint: str
    decision_status: str
    downstream_eligible: bool
    decision_fingerprint: str


@dataclass(frozen=True)
class FeatureSnapshotAdmissionIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


def evaluate_feature_snapshot_for_downstream(
    *,
    snapshot_fingerprint: str,
    snapshot_store: SQLiteFeatureSnapshotStore,
    feature_registry: SQLiteFeatureDefinitionRegistry,
    observation_store: SQLiteCanonicalObservationStore,
    expected_sport: str | None = None,
) -> FeatureSnapshotAdmissionDecision:
    snapshot_integrity = snapshot_store.audit_integrity()
    if not snapshot_integrity.ok:
        raise ValueError(
            "FEATURE_SNAPSHOT_STORE_INTEGRITY_FAILED"
        )

    feature_integrity = feature_registry.audit_integrity()
    if not feature_integrity.ok:
        raise ValueError(
            "FEATURE_DEFINITION_INTEGRITY_FAILED"
        )

    observation_integrity = observation_store.audit_integrity()
    if not observation_integrity.ok:
        raise ValueError(
            "CANONICAL_OBSERVATION_INTEGRITY_FAILED"
        )

    payload = snapshot_store.get_by_snapshot_fingerprint(
        snapshot_fingerprint
    )
    if payload is None:
        raise ValueError("FEATURE_SNAPSHOT_NOT_FOUND")

    sport = payload.get("sport")
    reasons: list[str] = []

    if sport not in {"football", "tennis"}:
        reasons.append("INVALID_SPORT")

    if (
        expected_sport is not None
        and sport != expected_sport
    ):
        reasons.append("SPORT_BOUNDARY_VIOLATION")

    try:
        feature_values = {
            item["feature_id"]: item.get("value")
            for item in payload.get("feature_values", [])
        }

        expected = build_point_in_time_feature_snapshot(
            sport=sport,
            entity_type=payload["entity_type"],
            canonical_id=payload["canonical_id"],
            feature_set_key=payload["feature_set_key"],
            feature_set_version=(
                payload["feature_set_version"]
            ),
            as_of=_parse_utc(payload["as_of"]),
            feature_values=feature_values,
            source_record_fingerprints=(
                payload["source_record_fingerprints"]
            ),
            feature_registry=feature_registry,
            observation_store=observation_store,
        )

        if (
            expected.snapshot_fingerprint
            != snapshot_fingerprint
        ):
            reasons.append(
                "SNAPSHOT_DERIVATION_MISMATCH"
            )

        if expected.payload() != payload:
            reasons.append(
                "SNAPSHOT_PAYLOAD_DERIVATION_MISMATCH"
            )
    except (KeyError, TypeError, ValueError) as error:
        reasons.append(
            "SNAPSHOT_REVALIDATION_FAILED:"
            + str(error)
        )

    reason_codes = tuple(dict.fromkeys(reasons))
    decision_status = (
        "ADMIT" if not reason_codes else "QUARANTINE"
    )
    downstream_eligible = decision_status == "ADMIT"

    base = {
        "schema": "matrix.feature-snapshot-admission/1",
        "sport": sport,
        "snapshot_fingerprint": snapshot_fingerprint,
        "decision_status": decision_status,
        "downstream_eligible": downstream_eligible,
        "reason_codes": list(reason_codes),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return FeatureSnapshotAdmissionDecision(
        sport=sport,
        snapshot_fingerprint=snapshot_fingerprint,
        decision_status=decision_status,
        downstream_eligible=downstream_eligible,
        reason_codes=reason_codes,
        decision_fingerprint=_sha(base),
    )


class SQLiteFeatureSnapshotAdmissionEvidenceLedger:
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
                CREATE TABLE IF NOT EXISTS
                feature_snapshot_admission_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    snapshot_fingerprint TEXT NOT NULL,
                    decision_status TEXT NOT NULL,
                    downstream_eligible INTEGER NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
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
    def _expected_decision_fingerprint(
        decision: FeatureSnapshotAdmissionDecision,
    ) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.feature-snapshot-admission/1"
                ),
                "sport": decision.sport,
                "snapshot_fingerprint": (
                    decision.snapshot_fingerprint
                ),
                "decision_status": (
                    decision.decision_status
                ),
                "downstream_eligible": (
                    decision.downstream_eligible
                ),
                "reason_codes": list(
                    decision.reason_codes
                ),
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }
        )

    def record_decision(
        self,
        decision: FeatureSnapshotAdmissionDecision,
    ) -> FeatureSnapshotAdmissionEvidence:
        expected_eligible = (
            decision.decision_status == "ADMIT"
        )

        if (
            decision.downstream_eligible
            is not expected_eligible
        ):
            raise ValueError(
                "FEATURE_SNAPSHOT_ELIGIBILITY_MISMATCH"
            )

        expected_fp = (
            self._expected_decision_fingerprint(
                decision
            )
        )

        if expected_fp != decision.decision_fingerprint:
            raise ValueError(
                "FEATURE_SNAPSHOT_DECISION_DERIVATION_MISMATCH"
            )

        evidence_id = _sha(
            {
                "schema": (
                    "matrix.feature-snapshot-admission-evidence-id/1"
                ),
                "snapshot_fingerprint": (
                    decision.snapshot_fingerprint
                ),
                "decision_fingerprint": (
                    decision.decision_fingerprint
                ),
            }
        )

        payload = {
            "schema": (
                "matrix.feature-snapshot-admission-evidence/1"
            ),
            "evidence_id": evidence_id,
            "sport": decision.sport,
            "snapshot_fingerprint": (
                decision.snapshot_fingerprint
            ),
            "decision_status": decision.decision_status,
            "downstream_eligible": (
                decision.downstream_eligible
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

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT evidence_id, payload_sha256
                FROM feature_snapshot_admission_evidence
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
                    return FeatureSnapshotAdmissionEvidence(
                        evidence_id=evidence_id,
                        sport=decision.sport,
                        snapshot_fingerprint=(
                            decision.snapshot_fingerprint
                        ),
                        decision_status=(
                            decision.decision_status
                        ),
                        downstream_eligible=(
                            decision.downstream_eligible
                        ),
                        decision_fingerprint=(
                            decision.decision_fingerprint
                        ),
                    )

                raise ValueError(
                    "FEATURE_SNAPSHOT_ADMISSION_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO
                    feature_snapshot_admission_evidence (
                        evidence_id,
                        sport,
                        snapshot_fingerprint,
                        decision_status,
                        downstream_eligible,
                        decision_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        decision.sport,
                        decision.snapshot_fingerprint,
                        decision.decision_status,
                        int(decision.downstream_eligible),
                        decision.decision_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "FEATURE_SNAPSHOT_ADMISSION_APPEND_ONLY_VIOLATION"
                ) from error

        return FeatureSnapshotAdmissionEvidence(
            evidence_id=evidence_id,
            sport=decision.sport,
            snapshot_fingerprint=(
                decision.snapshot_fingerprint
            ),
            decision_status=decision.decision_status,
            downstream_eligible=(
                decision.downstream_eligible
            ),
            decision_fingerprint=(
                decision.decision_fingerprint
            ),
        )

    def audit_integrity(
        self,
    ) -> FeatureSnapshotAdmissionIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    snapshot_fingerprint,
                    decision_status,
                    downstream_eligible,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM feature_snapshot_admission_evidence
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for row in rows:
            (
                evidence_id,
                sport,
                snapshot_fingerprint,
                decision_status,
                downstream_eligible,
                decision_fingerprint,
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
                    f"PAYLOAD_HASH_MISMATCH:"
                    f"{decision_fingerprint}"
                )

            expected_pairs = {
                "evidence_id": evidence_id,
                "sport": sport,
                "snapshot_fingerprint": (
                    snapshot_fingerprint
                ),
                "decision_status": decision_status,
                "downstream_eligible": bool(
                    downstream_eligible
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{decision_fingerprint}"
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

        return FeatureSnapshotAdmissionIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
