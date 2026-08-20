from app.core.feature_set_manifest_registry import (
    SQLiteFeatureSetManifestRegistry,
)


def test_feature_set_manifest_binds_exact_definitions(
    tmp_path,
):
    registry = SQLiteFeatureSetManifestRegistry(
        tmp_path / "sets.db"
    )

    manifest = registry.build_manifest(
        sport="tennis",
        entity_type="player",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=(
            "a" * 64,
            "b" * 64,
        ),
    )

    registry.register(manifest)
    replay = registry.register(manifest)

    assert (
        replay.manifest_fingerprint
        == manifest.manifest_fingerprint
    )


def test_feature_set_same_version_cannot_mutate(
    tmp_path,
):
    import pytest

    registry = SQLiteFeatureSetManifestRegistry(
        tmp_path / "sets.db"
    )

    registry.register(
        registry.build_manifest(
            sport="football",
            entity_type="team",
            feature_set_key="prematch.core",
            feature_set_version="1",
            feature_definition_fingerprints=(
                "a" * 64,
            ),
        )
    )

    changed = registry.build_manifest(
        sport="football",
        entity_type="team",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=(
            "a" * 64,
            "b" * 64,
        ),
    )

    with pytest.raises(
        ValueError,
        match="FEATURE_SET_VERSION_MUTATION_VIOLATION",
    ):
        registry.register(changed)


def test_duplicate_features_fail_closed(tmp_path):
    import pytest

    registry = SQLiteFeatureSetManifestRegistry(
        tmp_path / "sets.db"
    )

    with pytest.raises(
        ValueError,
        match="DUPLICATE_FEATURE_DEFINITION",
    ):
        registry.build_manifest(
            sport="tennis",
            entity_type="player",
            feature_set_key="x",
            feature_set_version="1",
            feature_definition_fingerprints=(
                "a" * 64,
                "a" * 64,
            ),
        )
