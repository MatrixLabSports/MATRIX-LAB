
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from app.application.football.identity_lifecycle import (
    append_football_temporal_provider_binding,
    remap_football_provider_identity,
)
from app.application.tennis.identity_lifecycle import (
    append_tennis_temporal_provider_binding,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.provider_identity_lifecycle import (
    SQLiteTemporalProviderIdentityLedger,
)


UTC = timezone.utc


def at(day: int) -> datetime:
    return datetime(
        2026,
        8,
        day,
        12,
        tzinfo=UTC,
    )


def prepared(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / "identity.db"
    )

    first = registry.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:F:237",
        display_name="Equipo A",
    )
    second = registry.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:F:238",
        display_name="Equipo B",
    )
    tennis = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:T:237",
        display_name="Jugador T",
    )

    registry.register(first)
    registry.register(second)
    registry.register(tennis)

    ledger = SQLiteTemporalProviderIdentityLedger(
        tmp_path / "provider-identity-lifecycle.db",
        identity_registry=registry,
    )

    return (
        registry,
        ledger,
        first,
        second,
        tennis,
    )


def append_initial(
    ledger,
    canonical_id,
):
    return append_football_temporal_provider_binding(
        ledger=ledger,
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        canonical_id=canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="INITIAL_BINDING",
        human_reviewed=False,
    )


def test_initial_temporal_binding_resolves_as_of(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    binding = append_initial(
        ledger,
        first.canonical_id,
    )

    resolved = ledger.resolve_as_of(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        as_of=at(5),
        event_time=at(3),
    )

    assert (
        resolved.binding_id
        == binding.binding_id
    )
    assert resolved.valid_from == at(1)
    assert resolved.valid_to is None
    assert ledger.audit_integrity().ok is True


def test_remap_is_bitemporal_and_closes_previous_interval(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        second,
        _,
    ) = prepared(
        tmp_path
    )

    initial = append_initial(
        ledger,
        first.canonical_id,
    )

    closed, successor = (
        remap_football_provider_identity(
            ledger=ledger,
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            new_canonical_id=(
                second.canonical_id
            ),
            remap_at=at(10),
            known_at=at(12),
            resolution_method="manual_verified",
            reason_code="PROVIDER_ID_REASSIGNED",
            human_reviewed=True,
        )
    )

    before_knowledge = ledger.resolve_as_of(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        as_of=at(11),
        event_time=at(10),
    )

    historical_after_knowledge = (
        ledger.resolve_as_of(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            as_of=at(12),
            event_time=at(9),
        )
    )

    remapped_after_knowledge = (
        ledger.resolve_as_of(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            as_of=at(12),
            event_time=at(10),
        )
    )

    assert (
        before_knowledge.canonical_id
        == first.canonical_id
    )
    assert (
        historical_after_knowledge.canonical_id
        == first.canonical_id
    )
    assert (
        remapped_after_knowledge.canonical_id
        == second.canonical_id
    )

    assert (
        closed.corrects_binding_id
        == initial.binding_id
    )
    assert closed.valid_from == at(1)
    assert closed.valid_to == at(10)
    assert (
        successor.predecessor_binding_id
        == closed.binding_id
    )
    assert successor.valid_from == at(10)
    assert successor.valid_to is None

    history = ledger.history(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
    )
    assert len(history) == 3


def test_remap_requires_human_review(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        second,
        _,
    ) = prepared(
        tmp_path
    )

    append_initial(
        ledger,
        first.canonical_id,
    )

    with pytest.raises(
        ValueError,
        match="PROVIDER_REMAP_REQUIRES_HUMAN_REVIEW",
    ):
        ledger.remap(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            new_canonical_id=(
                second.canonical_id
            ),
            remap_at=at(10),
            known_at=at(12),
            resolution_method="manual_verified",
            reason_code="PROVIDER_ID_REASSIGNED",
            human_reviewed=False,
        )


def test_temporal_binding_rejects_cross_sport_canonical_id(
    tmp_path,
):
    (
        _,
        ledger,
        _,
        _,
        tennis,
    ) = prepared(
        tmp_path
    )

    binding = ledger.build_binding(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        canonical_id=tennis.canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="INVALID",
        human_reviewed=False,
    )

    with pytest.raises(
        ValueError,
        match=(
            "TEMPORAL_PROVIDER_MAPPING_CANONICAL_SCOPE_MISMATCH"
        ),
    ):
        ledger.append(
            binding
        )


def test_valid_to_must_be_after_valid_from():
    with pytest.raises(
        ValueError,
        match=(
            "PROVIDER_MAPPING_INVALID_VALIDITY_WINDOW"
        ),
    ):
        from app.core.provider_identity_lifecycle import (
            build_temporal_provider_identity_binding,
        )

        build_temporal_provider_identity_binding(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            canonical_id="football:team:test",
            valid_from=at(5),
            valid_to=at(5),
            known_at=at(5),
            resolution_method="provider_stable_id",
            reason_code="INVALID",
            human_reviewed=False,
        )


def test_event_time_after_as_of_is_rejected(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    append_initial(
        ledger,
        first.canonical_id,
    )

    with pytest.raises(
        ValueError,
        match=(
            "PROVIDER_MAPPING_EVENT_TIME_AFTER_AS_OF"
        ),
    ):
        ledger.resolve_as_of(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
            as_of=at(3),
            event_time=at(4),
        )


def test_exact_binding_replay_is_idempotent(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    binding = append_initial(
        ledger,
        first.canonical_id,
    )

    replay = ledger.append(
        binding
    )

    assert (
        replay.binding_id
        == binding.binding_id
    )
    assert len(
        ledger.history(
            sport="football",
            entity_type="team",
            provider_key="provider-a",
            provider_entity_id="team-99",
        )
    ) == 1


def test_tennis_adapter_cannot_bind_football_identity(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match=(
            "TEMPORAL_PROVIDER_MAPPING_CANONICAL_SCOPE_MISMATCH"
        ),
    ):
        append_tennis_temporal_provider_binding(
            ledger=ledger,
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="p1",
            canonical_id=first.canonical_id,
            valid_from=at(1),
            valid_to=None,
            known_at=at(1),
            resolution_method="provider_stable_id",
            reason_code="INVALID",
            human_reviewed=False,
        )


def test_temporal_mapping_has_no_name_resolution_api(
    tmp_path,
):
    (
        _,
        ledger,
        _,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    assert not hasattr(
        ledger,
        "resolve_by_name",
    )
    assert not hasattr(
        ledger,
        "find_by_name",
    )


def test_temporal_mapping_tampering_is_detected(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    binding = append_initial(
        ledger,
        first.canonical_id,
    )

    with sqlite3.connect(
        ledger.path
    ) as connection:
        connection.execute(
            "UPDATE temporal_provider_identity_binding "
            "SET payload_json = ? WHERE binding_id = ?",
            (
                '{"tampered":true}\n',
                binding.binding_id,
            ),
        )
        connection.commit()

    assert (
        ledger.audit_integrity().ok
        is False
    )


def test_temporal_mapping_safety_flags_remain_false(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    binding = append_initial(
        ledger,
        first.canonical_id,
    )

    payload = binding.payload()

    assert payload["name_join_allowed"] is False
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False


def test_successor_cannot_be_known_before_predecessor(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        second,
        _,
    ) = prepared(
        tmp_path
    )

    initial = append_initial(
        ledger,
        first.canonical_id,
    )

    closed = ledger.build_binding(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        canonical_id=first.canonical_id,
        valid_from=at(1),
        valid_to=at(10),
        known_at=at(12),
        resolution_method="manual_verified",
        reason_code="CLOSE_FOR_REMAP",
        human_reviewed=True,
        corrects_binding_id=initial.binding_id,
    )

    ledger.append(
        closed
    )

    successor = ledger.build_binding(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        canonical_id=second.canonical_id,
        valid_from=at(10),
        valid_to=None,
        known_at=at(11),
        resolution_method="manual_verified",
        reason_code="RETROACTIVE_SUCCESSOR",
        human_reviewed=True,
        predecessor_binding_id=closed.binding_id,
    )

    with pytest.raises(
        ValueError,
        match=(
            "TEMPORAL_PROVIDER_MAPPING_SUCCESSOR_KNOWN_BEFORE_PREDECESSOR"
        ),
    ):
        ledger.append(
            successor
        )


def test_successor_may_share_atomic_known_at_with_predecessor(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        second,
        _,
    ) = prepared(
        tmp_path
    )

    append_initial(
        ledger,
        first.canonical_id,
    )

    closed, successor = ledger.remap(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-99",
        new_canonical_id=second.canonical_id,
        remap_at=at(10),
        known_at=at(12),
        resolution_method="manual_verified",
        reason_code="ATOMIC_REMAP",
        human_reviewed=True,
    )

    assert closed.known_at == at(12)
    assert successor.known_at == at(12)
    assert (
        successor.predecessor_binding_id
        == closed.binding_id
    )
