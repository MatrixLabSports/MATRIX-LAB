from datetime import datetime, timezone
import sqlite3

import pytest

from app.core.raw_schema_registry import (
    RawSchemaField,
    SQLiteRawSchemaRegistry,
)


UTC = timezone.utc


def contract(registry):
    return registry.build_contract(
        sport="tennis",
        entity_type="player",
        schema_name="tennis.player.match_history",
        schema_version="1",
        available_at=datetime(
            2026,
            8,
            1,
            tzinfo=UTC,
        ),
        fields=(
            RawSchemaField(
                name="event_key",
                value_type="string",
                required=True,
                nullable=False,
            ),
            RawSchemaField(
                name="aces",
                value_type="integer",
                required=False,
                nullable=True,
            ),
        ),
    )


def test_schema_contract_is_immutable_and_idempotent(
    tmp_path,
):
    registry = SQLiteRawSchemaRegistry(
        tmp_path / "schema.db"
    )
    value = contract(registry)

    first = registry.register(value)
    second = registry.register(value)

    assert first.schema_id == second.schema_id
    assert registry.audit_integrity().records == 1


def test_same_version_mutation_is_rejected(tmp_path):
    registry = SQLiteRawSchemaRegistry(
        tmp_path / "schema.db"
    )
    registry.register(contract(registry))

    changed = registry.build_contract(
        sport="tennis",
        entity_type="player",
        schema_name="tennis.player.match_history",
        schema_version="1",
        available_at=datetime(
            2026,
            8,
            1,
            tzinfo=UTC,
        ),
        fields=(
            RawSchemaField(
                name="event_key",
                value_type="string",
                required=True,
                nullable=False,
            ),
            RawSchemaField(
                name="aces",
                value_type="float",
                required=False,
                nullable=True,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="RAW_SCHEMA_VERSION_MUTATION_VIOLATION",
    ):
        registry.register(changed)


def test_cross_sport_contracts_have_distinct_fingerprints(
    tmp_path,
):
    registry = SQLiteRawSchemaRegistry(
        tmp_path / "schema.db"
    )

    tennis = contract(registry)
    football = registry.build_contract(
        sport="football",
        entity_type="team",
        schema_name="football.team.match_history",
        schema_version="1",
        available_at=datetime(
            2026,
            8,
            1,
            tzinfo=UTC,
        ),
        fields=(
            RawSchemaField(
                name="event_key",
                value_type="string",
                required=True,
                nullable=False,
            ),
        ),
    )

    assert (
        tennis.schema_fingerprint
        != football.schema_fingerprint
    )


def test_registry_tampering_is_detected(tmp_path):
    path = tmp_path / "schema.db"
    registry = SQLiteRawSchemaRegistry(path)
    value = contract(registry)
    registry.register(value)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE raw_schema_contracts
            SET payload_json = ?
            WHERE schema_id = ?
            """,
            (
                '{"tampered":true}\n',
                value.schema_id,
            ),
        )
        connection.commit()

    assert registry.audit_integrity().ok is False
