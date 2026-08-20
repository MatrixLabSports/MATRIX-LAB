import json
import sqlite3

import pytest

from app.core.feature_transformation_registry import (
    SQLiteFeatureTransformationRegistry,
    TransformationInput,
)


def transformation(registry, artifact="c" * 64):
    return registry.build_transformation(
        sport="tennis",
        entity_type="player",
        transformation_key="serve.form",
        transformation_version="1",
        artifact_sha256=artifact,
        output_feature_definition_fingerprints=("a" * 64,),
        inputs=(
            TransformationInput(
                schema_name="tennis.player.match_history",
                schema_version="1",
                fields=("aces", "double_faults"),
            ),
        ),
    )


def test_transformation_binds_artifact_and_exact_inputs(tmp_path):
    registry = SQLiteFeatureTransformationRegistry(
        tmp_path / "transforms.db"
    )
    value = transformation(registry)

    registry.register(value)
    loaded = registry.get_by_fingerprint(
        value.transformation_fingerprint
    )

    assert loaded["artifact_sha256"] == "c" * 64
    assert loaded["inputs"][0]["fields"] == [
        "aces",
        "double_faults",
    ]
    assert registry.audit_integrity().ok is True


def test_same_version_artifact_change_is_rejected(tmp_path):
    registry = SQLiteFeatureTransformationRegistry(
        tmp_path / "transforms.db"
    )
    registry.register(transformation(registry))

    with pytest.raises(
        ValueError,
        match="TRANSFORMATION_VERSION_MUTATION_VIOLATION",
    ):
        registry.register(
            transformation(registry, artifact="d" * 64)
        )


def test_verified_transformation_read_detects_semantic_tamper(tmp_path):
    path = tmp_path / "transforms.db"
    registry = SQLiteFeatureTransformationRegistry(path)
    value = transformation(registry)
    registry.register(value)

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM feature_transformations
                WHERE transformation_fingerprint = ?
                """,
                (value.transformation_fingerprint,),
            ).fetchone()[0]
        )
        payload["artifact_sha256"] = "f" * 64
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
            UPDATE feature_transformations
            SET payload_json = ?, payload_sha256 = ?
            WHERE transformation_fingerprint = ?
            """,
            (
                payload_json,
                payload_sha,
                value.transformation_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(ValueError):
        registry.get_by_fingerprint(
            value.transformation_fingerprint
        )
