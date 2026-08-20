from datetime import datetime, timezone

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
    path = tmp_path / "feature.db"

    identity = SQLiteCanonicalIdentityRegistry(path)
    entity = identity.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:T:400",
        display_name="Jugador 400",
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
            provider_entity_id="p400",
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
        provider_entity_id="p400",
        source_record_id="r400",
        schema_name="tennis.player.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        payload={"aces": 5},
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
        sport="tennis",
        entity_type="player",
        feature_name="serve.aces_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.player.stats",),
    )
    features.register(definition)

    return (
        entity,
        record,
        observations,
        features,
        definition,
    )


def test_feature_snapshot_binds_to_sources_and_definitions(
    tmp_path,
):
    (
        entity,
        record,
        observations,
        features,
        definition,
    ) = prepared(tmp_path)

    snapshot = build_point_in_time_feature_snapshot(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        feature_set_key="tennis.player.form",
        feature_set_version="1",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        feature_values={
            definition.feature_id: 0.25,
        },
        source_record_fingerprints=(
            record.record_fingerprint,
        ),
        feature_registry=features,
        observation_store=observations,
    )

    assert len(snapshot.snapshot_fingerprint) == 64
    assert (
        snapshot.definition_fingerprints
        == (definition.definition_fingerprint,)
    )


def test_missing_feature_value_is_preserved(tmp_path):
    (
        entity,
        record,
        observations,
        features,
        definition,
    ) = prepared(tmp_path)

    snapshot = build_point_in_time_feature_snapshot(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        feature_set_key="tennis.player.form",
        feature_set_version="1",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        feature_values={
            definition.feature_id: None,
        },
        source_record_fingerprints=(
            record.record_fingerprint,
        ),
        feature_registry=features,
        observation_store=observations,
    )

    assert snapshot.feature_values[0][1] is None
    assert snapshot.payload()["missing_is_zero"] is False


def test_future_source_record_is_rejected(tmp_path):
    (
        entity,
        record,
        observations,
        features,
        definition,
    ) = prepared(tmp_path)

    with pytest.raises(
        ValueError,
        match="FUTURE_SOURCE_RECORD_FOR_FEATURE",
    ):
        build_point_in_time_feature_snapshot(
            sport="tennis",
            entity_type="player",
            canonical_id=entity.canonical_id,
            feature_set_key="tennis.player.form",
            feature_set_version="1",
            as_of=datetime(
                2026,
                8,
                1,
                23,
                tzinfo=UTC,
            ),
            feature_values={
                definition.feature_id: 0.25,
            },
            source_record_fingerprints=(
                record.record_fingerprint,
            ),
            feature_registry=features,
            observation_store=observations,
        )


def test_cross_sport_feature_definition_is_rejected(tmp_path):
    (
        entity,
        record,
        observations,
        features,
        _,
    ) = prepared(tmp_path)

    football = features.build_definition(
        sport="football",
        entity_type="player",
        feature_name="attack.shots_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("football.player.stats",),
    )
    features.register(football)

    with pytest.raises(
        ValueError,
        match="FEATURE_SPORT_MISMATCH",
    ):
        build_point_in_time_feature_snapshot(
            sport="tennis",
            entity_type="player",
            canonical_id=entity.canonical_id,
            feature_set_key="tennis.player.form",
            feature_set_version="1",
            as_of=datetime(2026, 8, 2, tzinfo=UTC),
            feature_values={
                football.feature_id: 0.25,
            },
            source_record_fingerprints=(
                record.record_fingerprint,
            ),
            feature_registry=features,
            observation_store=observations,
        )


def test_undeclared_source_schema_is_rejected(tmp_path):
    (
        entity,
        record,
        observations,
        features,
        _,
    ) = prepared(tmp_path)

    definition = features.build_definition(
        sport="tennis",
        entity_type="player",
        feature_name="return.points_rate",
        feature_version="1",
        value_type="float",
        nullable=True,
        source_schema_names=("tennis.return.stats",),
    )
    features.register(definition)

    with pytest.raises(
        ValueError,
        match="UNDECLARED_SOURCE_SCHEMA",
    ):
        build_point_in_time_feature_snapshot(
            sport="tennis",
            entity_type="player",
            canonical_id=entity.canonical_id,
            feature_set_key="tennis.player.form",
            feature_set_version="1",
            as_of=datetime(2026, 8, 2, tzinfo=UTC),
            feature_values={
                definition.feature_id: 0.20,
            },
            source_record_fingerprints=(
                record.record_fingerprint,
            ),
            feature_registry=features,
            observation_store=observations,
        )


def test_snapshot_fingerprint_is_deterministic(tmp_path):
    (
        entity,
        record,
        observations,
        features,
        definition,
    ) = prepared(tmp_path)

    kwargs = dict(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        feature_set_key="tennis.player.form",
        feature_set_version="1",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        feature_values={
            definition.feature_id: 0.25,
        },
        source_record_fingerprints=(
            record.record_fingerprint,
        ),
        feature_registry=features,
        observation_store=observations,
    )

    first = build_point_in_time_feature_snapshot(**kwargs)
    second = build_point_in_time_feature_snapshot(**kwargs)

    assert (
        first.snapshot_fingerprint
        == second.snapshot_fingerprint
    )
