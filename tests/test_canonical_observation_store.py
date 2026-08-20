from dataclasses import replace
from datetime import datetime, timezone
import sqlite3

import pytest

from app.application.football.canonical_observation_store import (
    append_football_canonical_observation,
)
from app.application.tennis.canonical_observation_store import (
    append_tennis_canonical_observation,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_observation_store import (
    SQLiteCanonicalObservationStore,
)
from app.core.point_in_time_admission_evidence import (
    SQLitePointInTimeAdmissionEvidenceLedger,
)
from app.core.point_in_time_data_contract import (
    build_point_in_time_record,
    evaluate_point_in_time_record,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc


def prepared(tmp_path, *, sport="tennis"):
    path = tmp_path / "data.db"

    registry = SQLiteCanonicalIdentityRegistry(path)
    entity_type = "player"
    canonical_key = (
        "PLAYER:T:300"
        if sport == "tennis"
        else "PLAYER:F:300"
    )

    entity = registry.build_entity(
        sport=sport,
        entity_type=entity_type,
        canonical_key=canonical_key,
        display_name="Entidad 300",
    )
    registry.register(entity)

    mappings = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=registry,
    )
    mapping = mappings.build_mapping(
        sport=sport,
        entity_type=entity_type,
        provider_key="provider-a",
        provider_entity_id="p300",
        canonical_id=entity.canonical_id,
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    mappings.append(mapping)

    record = build_point_in_time_record(
        sport=sport,
        entity_type=entity_type,
        canonical_id=entity.canonical_id,
        provider_key="provider-a",
        provider_entity_id="p300",
        source_record_id="r300",
        schema_name=f"{sport}.player.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        payload={"metric": None, "other": 2},
    )

    decision = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
        expected_sport=sport,
    )

    evidence = SQLitePointInTimeAdmissionEvidenceLedger(
        path
    )
    evidence.record_decision(decision)

    store = SQLiteCanonicalObservationStore(path)

    return (
        path,
        entity,
        record,
        decision,
        evidence,
        store,
    )


def test_only_durably_admitted_record_can_be_stored(tmp_path):
    (
        _,
        entity,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path)

    observation = store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )

    stored = store.get_by_record_fingerprint(
        record.record_fingerprint
    )

    assert observation.canonical_id == entity.canonical_id
    assert stored["payload"]["metric"] is None
    assert stored["missing_is_zero"] is False


def test_missing_durable_admission_evidence_blocks_store(tmp_path):
    (
        path,
        _,
        record,
        decision,
        _,
        store,
    ) = prepared(tmp_path)

    empty_evidence = (
        SQLitePointInTimeAdmissionEvidenceLedger(
            tmp_path / "empty.db"
        )
    )

    with pytest.raises(
        ValueError,
        match="MISSING_DURABLE_ADMISSION_EVIDENCE",
    ):
        store.append_admitted_record(
            record=record,
            decision=decision,
            admission_evidence_ledger=empty_evidence,
        )


def test_quarantine_decision_cannot_enter_store(tmp_path):
    (
        _,
        _,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path)

    quarantine = replace(
        decision,
        decision_status="QUARANTINE",
        downstream_eligible=False,
    )

    with pytest.raises(
        ValueError,
        match="RECORD_NOT_ADMITTED",
    ):
        store.append_admitted_record(
            record=record,
            decision=quarantine,
            admission_evidence_ledger=evidence,
        )


def test_exact_replay_is_idempotent(tmp_path):
    (
        _,
        _,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path)

    first = store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )
    second = store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )

    assert first.observation_id == second.observation_id
    assert store.audit_integrity().records == 1


def test_list_as_of_never_returns_future_available_data(tmp_path):
    (
        _,
        entity,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path)

    store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )

    before = store.list_as_of(
        sport="tennis",
        canonical_id=entity.canonical_id,
        schema_name="tennis.player.stats",
        as_of=datetime(2026, 8, 1, 23, tzinfo=UTC),
    )
    after = store.list_as_of(
        sport="tennis",
        canonical_id=entity.canonical_id,
        schema_name="tennis.player.stats",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert before == ()
    assert len(after) == 1


def test_tampering_is_detected(tmp_path):
    (
        path,
        _,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path)

    store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE canonical_observations
            SET payload_json = ?
            WHERE record_fingerprint = ?
            """,
            ('{"tampered":true}\n', record.record_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity().ok is False


def test_sport_adapters_reject_cross_sport(tmp_path):
    (
        _,
        _,
        record,
        decision,
        evidence,
        store,
    ) = prepared(tmp_path, sport="tennis")

    observation = append_tennis_canonical_observation(
        store=store,
        record=record,
        decision=decision,
        admission_evidence_ledger=evidence,
    )
    assert observation.sport == "tennis"

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        append_football_canonical_observation(
            store=store,
            record=record,
            decision=decision,
            admission_evidence_ledger=evidence,
        )
