from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


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
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class FeatureSetManifest:
    manifest_id: str
    sport: str
    entity_type: str
    feature_set_key: str
    feature_set_version: str
    feature_definition_fingerprints: tuple[str, ...]
    manifest_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.feature-set-manifest/1",
            "manifest_id": self.manifest_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "feature_set_key": self.feature_set_key,
            "feature_set_version": self.feature_set_version,
            "feature_definition_fingerprints": list(
                self.feature_definition_fingerprints
            ),
            "manifest_fingerprint": self.manifest_fingerprint,
            "point_in_time_required": True,
            "missing_is_zero": False,
            "automatic_model_promotion": False,
        }


@dataclass(frozen=True)
class FeatureSetManifestIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteFeatureSetManifestRegistry:
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
                CREATE TABLE IF NOT EXISTS feature_set_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    feature_set_key TEXT NOT NULL,
                    feature_set_version TEXT NOT NULL,
                    manifest_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE (
                        sport,
                        entity_type,
                        feature_set_key,
                        feature_set_version
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def build_manifest(
        *,
        sport: str,
        entity_type: str,
        feature_set_key: str,
        feature_set_version: str,
        feature_definition_fingerprints: Sequence[str],
    ) -> FeatureSetManifest:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")

        for name, value in {
            "entity_type": entity_type,
            "feature_set_key": feature_set_key,
            "feature_set_version": feature_set_version,
        }.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"INVALID_{name.upper()}")

        if (
            isinstance(feature_definition_fingerprints, (str, bytes))
            or not isinstance(feature_definition_fingerprints, Sequence)
            or not feature_definition_fingerprints
        ):
            raise ValueError("EMPTY_FEATURE_SET")

        fingerprints = tuple(
            sorted(
                {
                    _hex64("FEATURE_DEFINITION_FINGERPRINT", value)
                    for value in feature_definition_fingerprints
                }
            )
        )

        if len(fingerprints) != len(feature_definition_fingerprints):
            raise ValueError("DUPLICATE_FEATURE_DEFINITION")

        base = {
            "schema": "matrix.feature-set-manifest/1",
            "sport": sport,
            "entity_type": entity_type,
            "feature_set_key": feature_set_key,
            "feature_set_version": feature_set_version,
            "feature_definition_fingerprints": list(fingerprints),
            "point_in_time_required": True,
            "missing_is_zero": False,
            "automatic_model_promotion": False,
        }

        manifest_fingerprint = _sha(base)
        manifest_id = _sha(
            {
                "schema": "matrix.feature-set-manifest-id/1",
                "manifest_fingerprint": manifest_fingerprint,
            }
        )

        return FeatureSetManifest(
            manifest_id=manifest_id,
            sport=sport,
            entity_type=entity_type,
            feature_set_key=feature_set_key,
            feature_set_version=feature_set_version,
            feature_definition_fingerprints=fingerprints,
            manifest_fingerprint=manifest_fingerprint,
        )

    @classmethod
    def _verify_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> FeatureSetManifest:
        expected = cls.build_manifest(
            sport=payload["sport"],
            entity_type=payload["entity_type"],
            feature_set_key=payload["feature_set_key"],
            feature_set_version=payload["feature_set_version"],
            feature_definition_fingerprints=payload[
                "feature_definition_fingerprints"
            ],
        )

        if expected.payload() != payload:
            raise ValueError("FEATURE_SET_SEMANTIC_INTEGRITY_VIOLATION")

        return expected

    def register(
        self,
        manifest: FeatureSetManifest,
    ) -> FeatureSetManifest:
        expected = self.build_manifest(
            sport=manifest.sport,
            entity_type=manifest.entity_type,
            feature_set_key=manifest.feature_set_key,
            feature_set_version=manifest.feature_set_version,
            feature_definition_fingerprints=(
                manifest.feature_definition_fingerprints
            ),
        )

        if expected != manifest:
            raise ValueError("FEATURE_SET_DERIVATION_MISMATCH")

        payload_json = _canonical_json(manifest.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT
                    manifest_id,
                    manifest_fingerprint,
                    payload_sha256
                FROM feature_set_manifests
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND feature_set_key = ?
                    AND feature_set_version = ?
                """,
                (
                    manifest.sport,
                    manifest.entity_type,
                    manifest.feature_set_key,
                    manifest.feature_set_version,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == manifest.manifest_id
                    and str(existing[1]) == manifest.manifest_fingerprint
                    and str(existing[2]) == payload_sha
                ):
                    return manifest
                raise ValueError("FEATURE_SET_VERSION_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO feature_set_manifests (
                    manifest_id,
                    sport,
                    entity_type,
                    feature_set_key,
                    feature_set_version,
                    manifest_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.manifest_id,
                    manifest.sport,
                    manifest.entity_type,
                    manifest.feature_set_key,
                    manifest.feature_set_version,
                    manifest.manifest_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return manifest

    def get_by_fingerprint(
        self,
        fingerprint: str,
    ) -> Mapping[str, Any] | None:
        fingerprint = _hex64("MANIFEST_FINGERPRINT", fingerprint)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    manifest_id,
                    manifest_fingerprint,
                    payload_json,
                    payload_sha256
                FROM feature_set_manifests
                WHERE manifest_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        manifest_id, stored_fp, payload_json, stored_sha = row
        payload = json.loads(payload_json)
        actual_sha = sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError("FEATURE_SET_PAYLOAD_HASH_MISMATCH")

        expected = self._verify_payload(payload)
        if (
            expected.manifest_id != manifest_id
            or expected.manifest_fingerprint != stored_fp
        ):
            raise ValueError("FEATURE_SET_REDERIVATION_MISMATCH")

        return payload

    def audit_integrity(self) -> FeatureSetManifestIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT manifest_fingerprint
                FROM feature_set_manifests
                ORDER BY manifest_id
                """
            ).fetchall()

        for (fingerprint,) in rows:
            try:
                self.get_by_fingerprint(fingerprint)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                errors.append(f"{error}:{fingerprint}")

        return FeatureSetManifestIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
