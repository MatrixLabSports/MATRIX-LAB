from datetime import datetime, timezone
import json
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
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
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


def test_schema_contract_is_immutable_and_idempotent(tmp_path):
    registry = SQLiteRawSchemaRegistry(tmp_path / "schema.db")
    value = contract(registry)

    first = registry.register(value)
    second = registry.register(value)

    assert first.schema_id == second.schema_id
    assert registry.audit_integrity().records == 1


def test_same_version_mutation_is_rejected(tmp_path):
    registry = SQLiteRawSchemaRegistry(tmp_path / "schema.db")
    registry.register(contract(registry))

    changed = registry.build_contract(
        sport="tennis",
        entity_type="player",
        schema_name="tennis.player.match_history",
        schema_version="1",
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
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


def test_verified_read_fails_closed_on_semantic_tamper(tmp_path):
    path = tmp_path / "schema.db"
    registry = SQLiteRawSchemaRegistry(path)
    value = contract(registry)
    registry.register(value)

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM raw_schema_contracts
                WHERE schema_id = ?
                """,
                (value.schema_id,),
            ).fetchone()[0]
        )
        payload["fields"][0]["value_type"] = "boolean"
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
            UPDATE raw_schema_contracts
            SET payload_json = ?, payload_sha256 = ?
            WHERE schema_id = ?
            """,
            (payload_json, payload_sha, value.schema_id),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="RAW_SCHEMA_INTEGRITY_VIOLATION",
    ):
        registry.get_exact(
            sport="tennis",
            entity_type="player",
            schema_name="tennis.player.match_history",
            schema_version="1",
        )

    assert registry.audit_integrity().ok is False
