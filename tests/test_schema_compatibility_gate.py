from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.raw_schema_registry import (
    RawSchemaField,
    SQLiteRawSchemaRegistry,
)
from app.core.schema_compatibility_gate import (
    evaluate_schema_compatibility,
)


UTC = timezone.utc


def registry(tmp_path):
    value = SQLiteRawSchemaRegistry(
        tmp_path / "schema.db"
    )
    value.register(
        value.build_contract(
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
                RawSchemaField(
                    name="xg_for",
                    value_type="number",
                    required=False,
                    nullable=True,
                ),
            ),
        )
    )
    return value


def test_exact_schema_is_admitted(tmp_path):
    gate = evaluate_schema_compatibility(
        record=SimpleNamespace(
            sport="football",
            schema_name="football.team.match_history",
            schema_version="1",
            payload={
                "event_key": "M:1",
                "xg_for": 1.2,
            },
        ),
        entity_type="team",
        as_of=datetime(
            2026,
            8,
            2,
            tzinfo=UTC,
        ),
        registry=registry(tmp_path),
    )

    assert gate.status == "ADMIT"
    assert gate.downstream_eligible is True


def test_unknown_schema_is_quarantined(tmp_path):
    gate = evaluate_schema_compatibility(
        record=SimpleNamespace(
            sport="football",
            schema_name="football.team.match_history",
            schema_version="99",
            payload={"event_key": "M:1"},
        ),
        entity_type="team",
        as_of=datetime(
            2026,
            8,
            2,
            tzinfo=UTC,
        ),
        registry=registry(tmp_path),
    )

    assert gate.status == "QUARANTINE"
    assert (
        "UNKNOWN_SCHEMA_VERSION"
        in gate.reason_codes
    )


def test_undeclared_field_is_drift_and_quarantined(
    tmp_path,
):
    gate = evaluate_schema_compatibility(
        record=SimpleNamespace(
            sport="football",
            schema_name="football.team.match_history",
            schema_version="1",
            payload={
                "event_key": "M:1",
                "new_field": 9,
            },
        ),
        entity_type="team",
        as_of=datetime(
            2026,
            8,
            2,
            tzinfo=UTC,
        ),
        registry=registry(tmp_path),
    )

    assert gate.status == "QUARANTINE"
    assert (
        "UNDECLARED_FIELD:new_field"
        in gate.reason_codes
    )


def test_missing_remains_missing_not_zero(tmp_path):
    gate = evaluate_schema_compatibility(
        record=SimpleNamespace(
            sport="football",
            schema_name="football.team.match_history",
            schema_version="1",
            payload={
                "event_key": "M:1",
                "xg_for": None,
            },
        ),
        entity_type="team",
        as_of=datetime(
            2026,
            8,
            2,
            tzinfo=UTC,
        ),
        registry=registry(tmp_path),
    )

    assert gate.status == "ADMIT"
