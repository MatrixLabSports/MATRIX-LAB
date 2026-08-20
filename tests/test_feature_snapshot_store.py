from datetime import datetime, timezone
import sqlite3

from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_observation_store import (
    SQLiteCanonicalObservationStore,
)
from app.core.feature_definition_registry import (
    SQLiteFeatureDefinitionRegistry,
)
from app.core.feature_snapshot_store import (
    SQLiteFeatureSnapshotStore,
)
from app.core.point_in_time_admission_evidence import (
    SQLitePointInTimeAdmissionEvidenceLedger,
)
from app.core.point_in_time_data_contract import (
    build_point_in_time_record,
    evaluate_point_in_time_record,
)
from app.core.point_in_time_feature_snapshot import (
    build_point_in_time_feature_snapshot,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc


def prepared(tmp_path):
    path = tmp_path / "snapshots.db"

    identity = SQLiteCanonicalIdentityRegistry(path)
    entity = identity.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:F:500",
        display_name="Equipo 500",
    )
    identity.register(entity)

    mappings = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=identity,
    )
    mappings.append(
        mappings.build_mapping(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="t500",
            canonical_id=entity.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    record = build_point_in_time_record(
        sport="football",
        entity_type="team",
        canonical_id=entity.canonical_id,
        provider_key="provider-a",
        provider_entity_id="t500",
        source_record_id="r500",
        schema_name="football.team.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        payload={"shots": 10},
    )
    decision = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        identity_registry=identity,
        mapping_ledger=mappings,
    )
    admission = SQLitePointInTimeAdmissionEvidenceLedger(
        path
    )
    admission.record_decision(decision)

    observations = SQLiteCanonicalObservationStore(path)
    observations.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=admission,
    )

    features = SQLiteFeatureDefinitionRegistry(path)
    definition = features.build_definition(
        sport="football",
        entity_type="team",
        feature_name="attack.shots_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("football.team.stats",),
    )
    features.register(definition)

    snapshot = build_point_in_time_feature_snapshot(
        sport="football",
        entity_type="team",
        canonical_id=entity.canonical_id,
        feature_set_key="football.team.form",
        feature_set_version="1",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        feature_values={
            definition.feature_id: 10.0,
        },
        source_record_fingerprints=(
            record.record_fingerprint,
        ),
        feature_registry=features,
        observation_store=observations,
    )

    store = SQLiteFeatureSnapshotStore(path)

    return (
        path,
        observations,
        features,
        snapshot,
        store,
    )


def test_snapshot_persists_immutably(tmp_path):
    (
        _,
        observations,
        features,
        snapshot,
        store,
    ) = prepared(tmp_path)

    evidence = store.record_snapshot(
        snapshot=snapshot,
        feature_registry=features,
        observation_store=observations,
    )

    payload = store.get_by_snapshot_fingerprint(
        snapshot.snapshot_fingerprint
    )

    assert evidence.snapshot_fingerprint == (
        snapshot.snapshot_fingerprint
    )
    assert payload["point_in_time_enforced"] is True
    assert store.audit_integrity().ok is True


def test_exact_replay_is_idempotent(tmp_path):
    (
        _,
        observations,
        features,
        snapshot,
        store,
    ) = prepared(tmp_path)

    first = store.record_snapshot(
        snapshot=snapshot,
        feature_registry=features,
        observation_store=observations,
    )
    second = store.record_snapshot(
        snapshot=snapshot,
        feature_registry=features,
        observation_store=observations,
    )

    assert first.evidence_id == second.evidence_id
    assert store.audit_integrity().records == 1


def test_snapshot_tampering_is_detected(tmp_path):
    (
        path,
        observations,
        features,
        snapshot,
        store,
    ) = prepared(tmp_path)

    store.record_snapshot(
        snapshot=snapshot,
        feature_registry=features,
        observation_store=observations,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE feature_snapshots
            SET payload_json = ?
            WHERE snapshot_fingerprint = ?
            """,
            (
                '{"tampered":true}\n',
                snapshot.snapshot_fingerprint,
            ),
        )
        connection.commit()

    assert store.audit_integrity().ok is False
