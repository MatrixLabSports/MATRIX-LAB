import json
import sqlite3

import pytest

from app.core.feature_set_manifest_registry import (
    SQLiteFeatureSetManifestRegistry,
)


def test_feature_set_manifest_binds_exact_definitions(tmp_path):
    registry = SQLiteFeatureSetManifestRegistry(tmp_path / "sets.db")

    manifest = registry.build_manifest(
        sport="tennis",
        entity_type="player",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=("a" * 64, "b" * 64),
    )

    registry.register(manifest)
    loaded = registry.get_by_fingerprint(
        manifest.manifest_fingerprint
    )

    assert loaded["manifest_id"] == manifest.manifest_id
    assert registry.audit_integrity().ok is True


def test_feature_set_same_version_cannot_mutate(tmp_path):
    registry = SQLiteFeatureSetManifestRegistry(tmp_path / "sets.db")

    registry.register(
        registry.build_manifest(
            sport="football",
            entity_type="team",
            feature_set_key="prematch.core",
            feature_set_version="1",
            feature_definition_fingerprints=("a" * 64,),
        )
    )

    changed = registry.build_manifest(
        sport="football",
        entity_type="team",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=("a" * 64, "b" * 64),
    )

    with pytest.raises(
        ValueError,
        match="FEATURE_SET_VERSION_MUTATION_VIOLATION",
    ):
        registry.register(changed)


def test_verified_feature_set_read_detects_semantic_tamper(tmp_path):
    path = tmp_path / "sets.db"
    registry = SQLiteFeatureSetManifestRegistry(path)
    manifest = registry.build_manifest(
        sport="tennis",
        entity_type="player",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=("a" * 64,),
    )
    registry.register(manifest)

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM feature_set_manifests
                WHERE manifest_fingerprint = ?
                """,
                (manifest.manifest_fingerprint,),
            ).fetchone()[0]
        )
        payload["feature_set_key"] = "tampered"
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        import hashlib
        payload_sha = hashlib.sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE feature_set_manifests
            SET payload_json = ?, payload_sha256 = ?
            WHERE manifest_fingerprint = ?
            """,
            (
                payload_json,
                payload_sha,
                manifest.manifest_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(ValueError):
        registry.get_by_fingerprint(
            manifest.manifest_fingerprint
        )
