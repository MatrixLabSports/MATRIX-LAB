from dataclasses import replace
import sqlite3

import pytest

from app.core.feature_definition_registry import (
    SQLiteFeatureDefinitionRegistry,
)


def test_feature_definition_is_deterministic_and_namespaced(
    tmp_path,
):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )

    first = registry.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="serve.aces_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.player.stats",),
    )
    second = registry.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="serve.aces_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.player.stats",),
    )

    assert first == second
    assert first.feature_id.startswith("tennis:player:")


def test_same_feature_name_across_sports_is_separate(tmp_path):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )

    tennis = registry.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="form.recent_score",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.player.stats",),
    )
    football = registry.build_definition(
        sport="football",
        entity_type="player",
        feature_name="form.recent_score",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("football.player.stats",),
    )

    assert tennis.feature_id != football.feature_id


def test_exact_replay_is_idempotent(tmp_path):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )
    definition = registry.build_definition(
        sport="football",
        entity_type="team",
        feature_name="attack.shots_on_target_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("football.team.stats",),
    )

    registry.register(definition)
    registry.register(definition)

    assert registry.audit_integrity().records == 1


def test_same_feature_version_cannot_mutate_semantics(tmp_path):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )
    original = registry.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="return.points_won_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.return.stats",),
    )
    registry.register(original)

    changed = registry.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="return.points_won_rate",
        feature_version="1",
        value_type="int",
        nullable=True,
        source_schema_names=("tennis.return.stats",),
    )

    with pytest.raises(
        ValueError,
        match="FEATURE_DEFINITION_MUTATION_VIOLATION",
    ):
        registry.register(changed)


def test_empty_source_schema_is_rejected(tmp_path):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )

    with pytest.raises(
        ValueError,
        match="EMPTY_SOURCE_SCHEMAS",
    ):
        registry.build_definition(
            sport="tennis",
            entity_type="player",
            feature_name="serve.hold_rate",
            feature_version="1",
            value_type="float",
            nullable=True,
            source_schema_names=(),
        )


def test_cross_sport_invalid_entity_type_is_rejected(tmp_path):
    registry = SQLiteFeatureDefinitionRegistry(
        tmp_path / "features.db"
    )

    with pytest.raises(
        ValueError,
        match="INVALID_ENTITY_TYPE_FOR_SPORT",
    ):
        registry.build_definition(
            sport="tennis",
            entity_type="team",
            feature_name="x.invalid",
            feature_version="1",
            value_type="float",
            nullable=True,
            source_schema_names=("tennis.x",),
        )


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "features.db"
    registry = SQLiteFeatureDefinitionRegistry(path)

    definition = registry.build_definition(
        sport="football",
        entity_type="team",
        feature_name="defense.xga_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("football.team.stats",),
    )
    registry.register(definition)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE feature_definitions
            SET payload_json = ?
            WHERE feature_id = ?
            """,
            ('{"tampered":true}\n', definition.feature_id),
        )
        connection.commit()

    assert registry.audit_integrity().ok is False
