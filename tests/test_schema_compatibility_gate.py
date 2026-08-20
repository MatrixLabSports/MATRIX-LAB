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
    value = SQLiteRawSchemaRegistry(tmp_path / "schema.db")
    value.register(
        value.build_contract(
            sport="football",
            entity_type="team",
            schema_name="football.team.match_history",
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
                    name="xg_for",
                    value_type="number",
                    required=False,
                    nullable=True,
                ),
            ),
        )
    )
    return value


def make_record(payload):
    return SimpleNamespace(
        sport="football",
        schema_name="football.team.match_history",
        schema_version="1",
        record_fingerprint="a" * 64,
        payload=payload,
    )


def test_exact_schema_is_admitted(tmp_path):
    gate = evaluate_schema_compatibility(
        record=make_record(
            {
                "event_key": "M:1",
                "xg_for": 1.2,
            }
        ),
        entity_type="team",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        registry=registry(tmp_path),
    )

    assert gate.status == "ADMIT"
    assert gate.downstream_eligible is True


def test_decision_fingerprint_binds_exact_payload(tmp_path):
    reg = registry(tmp_path)

    first = evaluate_schema_compatibility(
        record=make_record(
            {
                "event_key": "M:1",
                "xg_for": 1.2,
            }
        ),
        entity_type="team",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        registry=reg,
    )
    second = evaluate_schema_compatibility(
        record=make_record(
            {
                "event_key": "M:2",
                "xg_for": 1.2,
            }
        ),
        entity_type="team",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        registry=reg,
    )

    assert first.status == second.status == "ADMIT"
    assert first.payload_fingerprint != second.payload_fingerprint
    assert first.decision_fingerprint != second.decision_fingerprint


def test_unknown_schema_is_quarantined(tmp_path):
    record = make_record({"event_key": "M:1"})
    record.schema_version = "99"

    gate = evaluate_schema_compatibility(
        record=record,
        entity_type="team",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        registry=registry(tmp_path),
    )

    assert gate.status == "QUARANTINE"
    assert "UNKNOWN_SCHEMA_VERSION" in gate.reason_codes


def test_undeclared_field_is_drift_and_quarantined(tmp_path):
    gate = evaluate_schema_compatibility(
        record=make_record(
            {
                "event_key": "M:1",
                "new_field": 9,
            }
        ),
        entity_type="team",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        registry=registry(tmp_path),
    )

    assert gate.status == "QUARANTINE"
    assert "UNDECLARED_FIELD:new_field" in gate.reason_codes
