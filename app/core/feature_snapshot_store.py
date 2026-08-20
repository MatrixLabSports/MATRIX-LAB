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
from app.core.point_in_time_feature_snapshot import (
    PointInTimeFeatureSnapshot,
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


@dataclass(frozen=True)
class FeatureSnapshotEvidence:
    evidence_id: str
    sport: str
    canonical_id: str
    feature_set_key: str
    feature_set_version: str
    snapshot_fingerprint: str


@dataclass(frozen=True)
class FeatureSnapshotIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteFeatureSnapshotStore:
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
                CREATE TABLE IF NOT EXISTS feature_snapshots (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    feature_set_key TEXT NOT NULL,
                    feature_set_version TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    snapshot_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def evidence_id_for(
        snapshot: PointInTimeFeatureSnapshot,
    ) -> str:
        payload = {
            "schema": "matrix.feature-snapshot-evidence-id/1",
            "sport": snapshot.sport,
            "canonical_id": snapshot.canonical_id,
            "feature_set_key": snapshot.feature_set_key,
            "feature_set_version": snapshot.feature_set_version,
            "as_of": (
                snapshot.as_of
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "snapshot_fingerprint": (
                snapshot.snapshot_fingerprint
            ),
        }

        return sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _revalidate_snapshot(
        *,
        snapshot: PointInTimeFeatureSnapshot,
        feature_registry: SQLiteFeatureDefinitionRegistry,
        observation_store: SQLiteCanonicalObservationStore,
    ) -> None:
        expected = build_point_in_time_feature_snapshot(
            sport=snapshot.sport,
            entity_type=snapshot.entity_type,
            canonical_id=snapshot.canonical_id,
            feature_set_key=snapshot.feature_set_key,
            feature_set_version=snapshot.feature_set_version,
            as_of=snapshot.as_of,
            feature_values=dict(snapshot.feature_values),
            source_record_fingerprints=(
                snapshot.source_record_fingerprints
            ),
            feature_registry=feature_registry,
            observation_store=observation_store,
        )

        if expected != snapshot:
            raise ValueError(
                "FEATURE_SNAPSHOT_DERIVATION_MISMATCH"
            )

    def record_snapshot(
        self,
        *,
        snapshot: PointInTimeFeatureSnapshot,
        feature_registry: SQLiteFeatureDefinitionRegistry,
        observation_store: SQLiteCanonicalObservationStore,
    ) -> FeatureSnapshotEvidence:
        self._revalidate_snapshot(
            snapshot=snapshot,
            feature_registry=feature_registry,
            observation_store=observation_store,
        )

        payload_json = _canonical_json(
            snapshot.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        evidence_id = self.evidence_id_for(snapshot)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    payload_sha256
                FROM feature_snapshots
                WHERE snapshot_fingerprint = ?
                """,
                (snapshot.snapshot_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return FeatureSnapshotEvidence(
                        evidence_id=evidence_id,
                        sport=snapshot.sport,
                        canonical_id=snapshot.canonical_id,
                        feature_set_key=(
                            snapshot.feature_set_key
                        ),
                        feature_set_version=(
                            snapshot.feature_set_version
                        ),
                        snapshot_fingerprint=(
                            snapshot.snapshot_fingerprint
                        ),
                    )

                raise ValueError(
                    "FEATURE_SNAPSHOT_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO feature_snapshots (
                        evidence_id,
                        sport,
                        entity_type,
                        canonical_id,
                        feature_set_key,
                        feature_set_version,
                        as_of,
                        snapshot_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        snapshot.sport,
                        snapshot.entity_type,
                        snapshot.canonical_id,
                        snapshot.feature_set_key,
                        snapshot.feature_set_version,
                        (
                            snapshot.as_of
                            .astimezone(UTC)
                            .isoformat()
                            .replace("+00:00", "Z")
                        ),
                        snapshot.snapshot_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "FEATURE_SNAPSHOT_APPEND_ONLY_VIOLATION"
                ) from error

        return FeatureSnapshotEvidence(
            evidence_id=evidence_id,
            sport=snapshot.sport,
            canonical_id=snapshot.canonical_id,
            feature_set_key=snapshot.feature_set_key,
            feature_set_version=snapshot.feature_set_version,
            snapshot_fingerprint=snapshot.snapshot_fingerprint,
        )

    def get_by_snapshot_fingerprint(
        self,
        snapshot_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        if (
            not isinstance(snapshot_fingerprint, str)
            or len(snapshot_fingerprint) != 64
        ):
            raise ValueError(
                "INVALID_SNAPSHOT_FINGERPRINT"
            )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM feature_snapshots
                WHERE snapshot_fingerprint = ?
                """,
                (snapshot_fingerprint,),
            ).fetchone()

        return None if row is None else json.loads(row[0])

    def audit_integrity(
        self,
    ) -> FeatureSnapshotIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    entity_type,
                    canonical_id,
                    feature_set_key,
                    feature_set_version,
                    as_of,
                    snapshot_fingerprint,
                    payload_json,
                    payload_sha256
                FROM feature_snapshots
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for row in rows:
            (
                evidence_id,
                sport,
                entity_type,
                canonical_id,
                feature_set_key,
                feature_set_version,
                as_of,
                snapshot_fingerprint,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{snapshot_fingerprint}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:"
                    f"{snapshot_fingerprint}"
                )

            expected_pairs = {
                "sport": sport,
                "entity_type": entity_type,
                "canonical_id": canonical_id,
                "feature_set_key": feature_set_key,
                "feature_set_version": feature_set_version,
                "as_of": as_of,
                "snapshot_fingerprint": (
                    snapshot_fingerprint
                ),
                "point_in_time_enforced": True,
                "missing_is_zero": False,
                "name_join_used": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{snapshot_fingerprint}"
                    )

            expected_evidence_id = sha256(
                _canonical_json(
                    {
                        "schema": (
                            "matrix.feature-snapshot-evidence-id/1"
                        ),
                        "sport": sport,
                        "canonical_id": canonical_id,
                        "feature_set_key": feature_set_key,
                        "feature_set_version": (
                            feature_set_version
                        ),
                        "as_of": as_of,
                        "snapshot_fingerprint": (
                            snapshot_fingerprint
                        ),
                    }
                ).encode("utf-8")
            ).hexdigest()

            if evidence_id != expected_evidence_id:
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:"
                    f"{snapshot_fingerprint}"
                )

        return FeatureSnapshotIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
