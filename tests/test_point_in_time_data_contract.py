from datetime import datetime, timezone

from app.application.football.point_in_time_data_contract import (
    evaluate_football_point_in_time_record,
)
from app.application.tennis.point_in_time_data_contract import (
    evaluate_tennis_point_in_time_record,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.point_in_time_data_contract import (
    build_point_in_time_record,
    evaluate_point_in_time_record,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc


def prepared(tmp_path):
    path = tmp_path / "data.db"

    registry = SQLiteCanonicalIdentityRegistry(path)
    entity = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:100",
        display_name="Jugador 100",
    )
    registry.register(entity)

    mappings = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=registry,
    )

    mapping = mappings.build_mapping(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="p100",
        canonical_id=entity.canonical_id,
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    mappings.append(mapping)

    return registry, mappings, entity


def make_record(entity, **overrides):
    kwargs = dict(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        provider_key="provider-a",
        provider_entity_id="p100",
        source_record_id="r1",
        schema_name="tennis.player.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 3, tzinfo=UTC),
        payload={"aces": None, "double_faults": 2},
    )
    kwargs.update(overrides)
    return build_point_in_time_record(**kwargs)


def test_data_and_mapping_must_both_exist_as_of(tmp_path):
    registry, mappings, entity = prepared(tmp_path)
    record = make_record(entity)

    before = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 2, 12, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )
    after = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    assert before.decision_status == "QUARANTINE"
    assert "DATA_NOT_AVAILABLE_AS_OF" in before.reason_codes
    assert after.decision_status == "ADMIT"
    assert after.downstream_eligible is True


def test_missing_values_remain_none_not_zero(tmp_path):
    _, _, entity = prepared(tmp_path)
    record = make_record(
        entity,
        payload={"aces": None},
    )

    assert record.payload["aces"] is None
    assert record.evidence_payload()["missing_is_zero"] is False


def test_mapping_not_available_as_of_quarantines(tmp_path):
    registry, mappings, entity = prepared(tmp_path)
    record = make_record(
        entity,
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    decision = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 1, 12, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    assert decision.decision_status == "QUARANTINE"
    assert (
        "PROVIDER_MAPPING_NOT_AVAILABLE_AS_OF"
        in decision.reason_codes
    )


def test_later_mapping_correction_can_quarantine_old_binding(
    tmp_path,
):
    registry, mappings, first = prepared(tmp_path)

    second = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:101",
        display_name="Jugador 101",
    )
    registry.register(second)

    mappings.append(
        mappings.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="p100",
            canonical_id=second.canonical_id,
            resolution_method="manual_verified",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 5, tzinfo=UTC),
        )
    )

    record = make_record(
        first,
        available_at=datetime(2026, 8, 3, tzinfo=UTC),
    )

    earlier = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 4, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )
    later = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    assert earlier.decision_status == "ADMIT"
    assert later.decision_status == "QUARANTINE"
    assert (
        "PROVIDER_MAPPING_CANONICAL_MISMATCH"
        in later.reason_codes
    )


def test_record_fingerprint_changes_with_available_at(tmp_path):
    _, _, entity = prepared(tmp_path)

    first = make_record(
        entity,
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    second = make_record(
        entity,
        available_at=datetime(2026, 8, 3, tzinfo=UTC),
    )

    assert first.record_fingerprint != second.record_fingerprint


def test_record_fingerprint_changes_with_schema_version(tmp_path):
    _, _, entity = prepared(tmp_path)

    first = make_record(entity, schema_version="1")
    second = make_record(entity, schema_version="2")

    assert first.record_fingerprint != second.record_fingerprint


def test_sport_adapters_fail_closed_for_wrong_sport(tmp_path):
    registry, mappings, entity = prepared(tmp_path)
    record = make_record(entity)

    tennis = evaluate_tennis_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )
    football = evaluate_football_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    assert tennis.decision_status == "ADMIT"
    assert football.decision_status == "QUARANTINE"
    assert "SPORT_BOUNDARY_VIOLATION" in football.reason_codes


def test_admission_decision_is_deterministic(tmp_path):
    registry, mappings, entity = prepared(tmp_path)
    record = make_record(entity)
    as_of = datetime(2026, 8, 3, tzinfo=UTC)

    first = evaluate_point_in_time_record(
        record=record,
        as_of=as_of,
        identity_registry=registry,
        mapping_ledger=mappings,
    )
    second = evaluate_point_in_time_record(
        record=record,
        as_of=as_of,
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    assert first.decision_fingerprint == second.decision_fingerprint
