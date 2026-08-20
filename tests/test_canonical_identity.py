from dataclasses import replace
import sqlite3

import pytest

from app.application.football.canonical_identity import (
    register_football_entity,
)
from app.application.tennis.canonical_identity import (
    register_tennis_entity,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
    make_canonical_id,
)


def test_canonical_id_is_deterministic():
    first = make_canonical_id(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:COL:001",
    )
    second = make_canonical_id(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:COL:001",
    )

    assert first == second
    assert first.startswith("football:team:")


def test_same_key_is_namespaced_by_sport():
    football = make_canonical_id(
        sport="football",
        entity_type="player",
        canonical_key="PLAYER:001",
    )
    tennis = make_canonical_id(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:001",
    )

    assert football != tennis


def test_football_team_registration_is_durable(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    entity = register_football_entity(
        registry=registry,
        entity_type="team",
        canonical_key="TEAM:COL:001",
        display_name="Equipo Ejemplo",
    )

    stored = registry.get_by_canonical_id(entity.canonical_id)

    assert stored["sport"] == "football"
    assert stored["entity_type"] == "team"
    assert stored["canonical_key"] == "TEAM:COL:001"
    assert stored["name_join_allowed"] is False


def test_tennis_player_registration_is_durable(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    entity = register_tennis_entity(
        registry=registry,
        entity_type="player",
        canonical_key="PLAYER:ATP:001",
        display_name="Jugador Ejemplo",
    )

    stored = registry.get_by_key(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:001",
    )

    assert stored["canonical_id"] == entity.canonical_id


def test_exact_replay_is_idempotent(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )
    entity = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:002",
        display_name="Jugador Dos",
    )

    first = registry.register(entity)
    second = registry.register(entity)

    assert first == second
    assert registry.audit_integrity().records == 1


def test_same_canonical_key_cannot_silently_change_name(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )
    original = registry.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:COL:002",
        display_name="Nombre Original",
    )
    registry.register(original)

    changed = registry.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:COL:002",
        display_name="Nombre Diferente",
    )

    with pytest.raises(
        ValueError,
        match="CANONICAL_IDENTITY_MUTATION_VIOLATION",
    ):
        registry.register(changed)


def test_football_team_type_is_not_valid_for_tennis(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    with pytest.raises(
        ValueError,
        match="INVALID_ENTITY_TYPE_FOR_SPORT",
    ):
        register_tennis_entity(
            registry=registry,
            entity_type="team",
            canonical_key="TEAM:001",
            display_name="No Permitido",
        )


def test_invalid_or_name_like_free_text_key_is_rejected():
    with pytest.raises(
        ValueError,
        match="INVALID_CANONICAL_KEY",
    ):
        make_canonical_id(
            sport="football",
            entity_type="team",
            canonical_key="Real Madrid CF",
        )


def test_registry_has_no_name_lookup_api(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    assert not hasattr(registry, "get_by_name")
    assert not hasattr(registry, "resolve_by_name")
    assert not hasattr(registry, "find_by_name")


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "identity.db"
    registry = SQLiteCanonicalIdentityRegistry(path)

    entity = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:003",
        display_name="Jugador Tres",
    )
    registry.register(entity)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE canonical_entities
            SET payload_json = ?
            WHERE canonical_id = ?
            """,
            ('{"tampered":true}\n', entity.canonical_id),
        )
        connection.commit()

    report = registry.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_derived_entity_mismatch_is_rejected(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    entity = registry.build_entity(
        sport="football",
        entity_type="player",
        canonical_key="PLAYER:COL:004",
        display_name="Jugador Cuatro",
    )

    tampered = replace(
        entity,
        canonical_id="football:player:" + ("0" * 64),
    )

    with pytest.raises(
        ValueError,
        match="CANONICAL_ENTITY_DERIVATION_MISMATCH",
    ):
        registry.register(tampered)


def test_safety_flags_remain_false(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    entity = registry.build_entity(
        sport="football",
        entity_type="competition",
        canonical_key="COMP:COL:001",
        display_name="Competicion Ejemplo",
    )
    registry.register(entity)

    payload = registry.get_by_canonical_id(entity.canonical_id)

    assert payload["name_join_allowed"] is False
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
