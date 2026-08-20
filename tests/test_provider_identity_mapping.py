from datetime import datetime, timezone
import sqlite3

import pytest

from app.application.football.provider_identity_mapping import (
    append_football_provider_identity_mapping,
)
from app.application.tennis.provider_identity_mapping import (
    append_tennis_provider_identity_mapping,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc


def registry_and_ledger(tmp_path):
    path = tmp_path / "identity.db"
    registry = SQLiteCanonicalIdentityRegistry(path)
    ledger = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=registry,
    )
    return registry, ledger


def register(
    registry,
    *,
    sport="tennis",
    entity_type="player",
    key="PLAYER:001",
    name="Entidad Uno",
):
    entity = registry.build_entity(
        sport=sport,
        entity_type=entity_type,
        canonical_key=key,
        display_name=name,
    )
    registry.register(entity)
    return entity


def test_provider_mapping_is_point_in_time(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    entity = register(registry)

    mapping = ledger.build_mapping(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="12345",
        canonical_id=entity.canonical_id,
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    ledger.append(mapping)

    assert ledger.resolve_as_of(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="12345",
        as_of=datetime(2026, 8, 1, 23, tzinfo=UTC),
    ) is None

    resolved = ledger.resolve_as_of(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="12345",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert resolved["canonical_id"] == entity.canonical_id


def test_name_based_resolution_is_forbidden(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    entity = register(registry)

    with pytest.raises(
        ValueError,
        match="NAME_BASED_IDENTITY_RESOLUTION_FORBIDDEN",
    ):
        ledger.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="123",
            canonical_id=entity.canonical_id,
            resolution_method="fuzzy_name",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_naive_timestamp_is_rejected(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    entity = register(registry)

    with pytest.raises(
        ValueError,
        match="INVALID_OBSERVED_AT",
    ):
        ledger.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="123",
            canonical_id=entity.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 1),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_available_at_cannot_precede_observed_at(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    entity = register(registry)

    with pytest.raises(
        ValueError,
        match="AVAILABLE_AT_BEFORE_OBSERVED_AT",
    ):
        ledger.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="123",
            canonical_id=entity.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 2, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_cross_sport_canonical_mapping_is_rejected(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    football = register(
        registry,
        sport="football",
        entity_type="player",
        key="PLAYER:F:001",
    )

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        ledger.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="123",
            canonical_id=football.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_later_correction_does_not_rewrite_earlier_as_of(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    first = register(
        registry,
        key="PLAYER:001",
        name="Jugador Uno",
    )
    second = register(
        registry,
        key="PLAYER:002",
        name="Jugador Dos",
    )

    for canonical_id, available_day in (
        (first.canonical_id, 2),
        (second.canonical_id, 5),
    ):
        ledger.append(
            ledger.build_mapping(
                sport="tennis",
                entity_type="player",
                provider_key="provider-a",
                provider_entity_id="123",
                canonical_id=canonical_id,
                resolution_method="manual_verified",
                observed_at=datetime(
                    2026,
                    8,
                    1,
                    tzinfo=UTC,
                ),
                available_at=datetime(
                    2026,
                    8,
                    available_day,
                    tzinfo=UTC,
                ),
            )
        )

    earlier = ledger.resolve_as_of(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="123",
        as_of=datetime(2026, 8, 4, tzinfo=UTC),
    )
    later = ledger.resolve_as_of(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="123",
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
    )

    assert earlier["canonical_id"] == first.canonical_id
    assert later["canonical_id"] == second.canonical_id


def test_same_time_conflicting_mapping_is_ambiguous(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    first = register(registry, key="PLAYER:003")
    second = register(registry, key="PLAYER:004")

    for canonical_id in (
        first.canonical_id,
        second.canonical_id,
    ):
        ledger.append(
            ledger.build_mapping(
                sport="tennis",
                entity_type="player",
                provider_key="provider-a",
                provider_entity_id="ambiguous",
                canonical_id=canonical_id,
                resolution_method="manual_verified",
                observed_at=datetime(
                    2026,
                    8,
                    1,
                    tzinfo=UTC,
                ),
                available_at=datetime(
                    2026,
                    8,
                    2,
                    tzinfo=UTC,
                ),
            )
        )

    with pytest.raises(
        ValueError,
        match="AMBIGUOUS_PROVIDER_MAPPING_AS_OF",
    ):
        ledger.resolve_as_of(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="ambiguous",
            as_of=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_exact_replay_is_idempotent(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    entity = register(registry)

    mapping = ledger.build_mapping(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="123",
        canonical_id=entity.canonical_id,
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    ledger.append(mapping)
    ledger.append(mapping)

    assert ledger.audit_integrity().records == 1


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "identity.db"
    registry = SQLiteCanonicalIdentityRegistry(path)
    entity = register(registry)
    ledger = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=registry,
    )

    mapping = ledger.build_mapping(
        sport="tennis",
        entity_type="player",
        provider_key="provider-a",
        provider_entity_id="123",
        canonical_id=entity.canonical_id,
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    ledger.append(mapping)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE provider_identity_mappings
            SET payload_json = ?
            WHERE mapping_id = ?
            """,
            ('{"tampered":true}\n', mapping.mapping_id),
        )
        connection.commit()

    assert ledger.audit_integrity().ok is False


def test_sport_adapters_create_only_expected_sport(tmp_path):
    registry, ledger = registry_and_ledger(tmp_path)
    tennis = register(
        registry,
        sport="tennis",
        key="PLAYER:T:010",
    )
    football = register(
        registry,
        sport="football",
        entity_type="team",
        key="TEAM:F:010",
    )

    tennis_mapping = append_tennis_provider_identity_mapping(
        ledger=ledger,
        provider_key="provider-a",
        provider_entity_id="t10",
        canonical_id=tennis.canonical_id,
        entity_type="player",
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    football_mapping = append_football_provider_identity_mapping(
        ledger=ledger,
        provider_key="provider-b",
        provider_entity_id="f10",
        canonical_id=football.canonical_id,
        entity_type="team",
        resolution_method="provider_stable_id",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert tennis_mapping.sport == "tennis"
    assert football_mapping.sport == "football"
