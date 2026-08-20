from datetime import datetime, timezone
import sqlite3

import pytest

from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_observation_store import (
    SQLiteCanonicalObservationStore,
)
from app.core.feature_definition_registry import (
    SQLiteFeatureDefinitionRegistry,
)
from app.core.feature_snapshot_admission import (
    SQLiteFeatureSnapshotAdmissionEvidenceLedger,
    evaluate_feature_snapshot_for_downstream,
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
    path = tmp_path / "admission.db"

    identity = SQLiteCanonicalIdentityRegistry(path)
    entity = identity.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:T:600",
        display_name="Jugador 600",
    )
    identity.register(entity)

    mappings = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=identity,
    )
    mappings.append(
        mappings.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="p600",
            canonical_id=entity.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    record = build_point_in_time_record(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        provider_key="provider-a",
        provider_entity_id="p600",
        source_record_id="r600",
        schema_name="tennis.player.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        payload={"aces": 7},
    )
    data_decision = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        identity_registry=identity,
        mapping_ledger=mappings,
    )
    data_evidence = SQLitePointInTimeAdmissionEvidenceLedger(
        path
    )
    data_evidence.record_decision(data_decision)

    observations = SQLiteCanonicalObservationStore(path)
    observations.append_admitted_record(
        record=record,
        decision=data_decision,
        admission_evidence_ledger=data_evidence,
    )

    features = SQLiteFeatureDefinitionRegistry(path)
    definition = features.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="serve.aces_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.player.stats",),
    )
    features.register(definition)

    snapshot = build_point_in_time_feature_snapshot(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        feature_set_key="tennis.player.form",
        feature_set_version="1",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        feature_values={
            definition.feature_id: 0.35,
        },
        source_record_fingerprints=(
            record.record_fingerprint,
        ),
        feature_registry=features,
        observation_store=observations,
    )

    snapshots = SQLiteFeatureSnapshotStore(path)
    snapshots.record_snapshot(
        snapshot=snapshot,
        feature_registry=features,
        observation_store=observations,
    )

    return (
        path,
        observations,
        features,
        snapshot,
        snapshots,
    )


def test_valid_snapshot_is_admitted_for_downstream(tmp_path):
    (
        path,
        observations,
        features,
        snapshot,
        snapshots,
    ) = prepared(tmp_path)

    decision = evaluate_feature_snapshot_for_downstream(
        snapshot_fingerprint=(
            snapshot.snapshot_fingerprint
        ),
        snapshot_store=snapshots,
        feature_registry=features,
        observation_store=observations,
        expected_sport="tennis",
    )

    evidence_ledger = (
        SQLiteFeatureSnapshotAdmissionEvidenceLedger(
            path
        )
    )
    evidence = evidence_ledger.record_decision(
        decision
    )

    assert decision.decision_status == "ADMIT"
    assert decision.downstream_eligible is True
    assert evidence.downstream_eligible is True
    assert evidence_ledger.audit_integrity().ok is True


def test_cross_sport_use_is_quarantined(tmp_path):
    (
        _,
        observations,
        features,
        snapshot,
        snapshots,
    ) = prepared(tmp_path)

    decision = evaluate_feature_snapshot_for_downstream(
        snapshot_fingerprint=(
            snapshot.snapshot_fingerprint
        ),
        snapshot_store=snapshots,
        feature_registry=features,
        observation_store=observations,
        expected_sport="football",
    )

    assert decision.decision_status == "QUARANTINE"
    assert (
        "SPORT_BOUNDARY_VIOLATION"
        in decision.reason_codes
    )


def test_tampered_snapshot_store_fails_closed(tmp_path):
    (
        path,
        observations,
        features,
        snapshot,
        snapshots,
    ) = prepared(tmp_path)

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

    with pytest.raises(
        ValueError,
        match="FEATURE_SNAPSHOT_STORE_INTEGRITY_FAILED",
    ):
        evaluate_feature_snapshot_for_downstream(
            snapshot_fingerprint=(
                snapshot.snapshot_fingerprint
            ),
            snapshot_store=snapshots,
            feature_registry=features,
            observation_store=observations,
            expected_sport="tennis",
        )


def test_admission_evidence_replay_is_idempotent(tmp_path):
    (
        path,
        observations,
        features,
        snapshot,
        snapshots,
    ) = prepared(tmp_path)

    decision = evaluate_feature_snapshot_for_downstream(
        snapshot_fingerprint=(
            snapshot.snapshot_fingerprint
        ),
        snapshot_store=snapshots,
        feature_registry=features,
        observation_store=observations,
        expected_sport="tennis",
    )

    ledger = SQLiteFeatureSnapshotAdmissionEvidenceLedger(
        path
    )

    first = ledger.record_decision(decision)
    second = ledger.record_decision(decision)

    assert first.evidence_id == second.evidence_id
    assert ledger.audit_integrity().records == 1


def test_admission_evidence_tampering_is_detected(tmp_path):
    (
        path,
        observations,
        features,
        snapshot,
        snapshots,
    ) = prepared(tmp_path)

    decision = evaluate_feature_snapshot_for_downstream(
        snapshot_fingerprint=(
            snapshot.snapshot_fingerprint
        ),
        snapshot_store=snapshots,
        feature_registry=features,
        observation_store=observations,
        expected_sport="tennis",
    )

    ledger = SQLiteFeatureSnapshotAdmissionEvidenceLedger(
        path
    )
    ledger.record_decision(decision)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE feature_snapshot_admission_evidence
            SET payload_json = ?
            WHERE decision_fingerprint = ?
            """,
            (
                '{"tampered":true}\n',
                decision.decision_fingerprint,
            ),
        )
        connection.commit()

    assert ledger.audit_integrity().ok is False
