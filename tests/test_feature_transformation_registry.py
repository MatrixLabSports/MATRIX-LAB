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
        output_feature_definition_fingerprints=(
            "a" * 64,
        ),
        inputs=(
            TransformationInput(
                schema_name="tennis.player.match_history",
                schema_version="1",
                fields=(
                    "aces",
                    "double_faults",
                ),
            ),
        ),
    )


def test_transformation_binds_artifact_and_exact_inputs(
    tmp_path,
):
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


def test_same_version_artifact_change_is_rejected(
    tmp_path,
):
    registry = SQLiteFeatureTransformationRegistry(
        tmp_path / "transforms.db"
    )
    registry.register(
        transformation(registry)
    )

    with pytest.raises(
        ValueError,
        match="TRANSFORMATION_VERSION_MUTATION_VIOLATION",
    ):
        registry.register(
            transformation(
                registry,
                artifact="d" * 64,
            )
        )


def test_duplicate_input_fields_fail_closed(
    tmp_path,
):
    registry = SQLiteFeatureTransformationRegistry(
        tmp_path / "transforms.db"
    )

    with pytest.raises(
        ValueError,
        match="DUPLICATE_TRANSFORMATION_INPUT_FIELD",
    ):
        registry.build_transformation(
            sport="football",
            entity_type="team",
            transformation_key="attack.form",
            transformation_version="1",
            artifact_sha256="e" * 64,
            output_feature_definition_fingerprints=(
                "a" * 64,
            ),
            inputs=(
                TransformationInput(
                    schema_name="football.team.match_history",
                    schema_version="1",
                    fields=("xg_for", "xg_for"),
                ),
            ),
        )
