
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from app.application.football.identity_lifecycle import (
    append_football_identity_alias,
    append_football_identity_rename,
    append_football_identity_supersession,
)
from app.application.tennis.identity_lifecycle import (
    append_tennis_identity_alias,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_identity_lifecycle import (
    SQLiteCanonicalIdentityLifecycleLedger,
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
        canonical_key="TEAM:F:137",
        display_name="Equipo Original",
    )
    second = registry.build_entity(
        sport="football",
        entity_type="team",
        canonical_key="TEAM:F:138",
        display_name="Equipo Sucesor",
    )
    tennis = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:T:137",
        display_name="Jugador",
    )

    registry.register(first)
    registry.register(second)
    registry.register(tennis)

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        tmp_path / "identity-lifecycle.db",
        identity_registry=registry,
    )

    return (
        registry,
        ledger,
        first,
        second,
        tennis,
    )


def test_alias_is_append_only_and_not_visible_before_known_at(
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

    event = append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Nombre Historico",
        effective_at=at(1),
        known_at=at(2),
        reason_code="VERIFIED_ALIAS",
    )

    before = ledger.state_as_of(
        canonical_id=first.canonical_id,
        as_of=at(1),
        event_time=at(1),
    )
    after = ledger.state_as_of(
        canonical_id=first.canonical_id,
        as_of=at(2),
        event_time=at(1),
    )

    assert before.aliases == ()
    assert after.aliases == (
        "Nombre Historico",
    )
    assert (
        ledger.append(event).event_id
        == event.event_id
    )
    assert ledger.audit_integrity().ok is True


def test_rename_is_lifecycle_evidence_not_canonical_row_mutation(
    tmp_path,
):
    (
        registry,
        ledger,
        first,
        _,
        _,
    ) = prepared(
        tmp_path
    )

    alias = append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Alias",
        effective_at=at(1),
        known_at=at(2),
        reason_code="VERIFIED_ALIAS",
    )

    rename = append_football_identity_rename(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        display_name="Equipo Renombrado",
        effective_at=at(2),
        known_at=at(3),
        reason_code="OFFICIAL_RENAME",
        previous_event_id=alias.event_id,
        human_reviewed=True,
    )

    before = ledger.state_as_of(
        canonical_id=first.canonical_id,
        as_of=at(2),
        event_time=at(2),
    )
    after = ledger.state_as_of(
        canonical_id=first.canonical_id,
        as_of=at(3),
        event_time=at(2),
    )

    assert (
        before.display_name
        == "Equipo Original"
    )
    assert (
        after.display_name
        == "Equipo Renombrado"
    )
    assert (
        registry.get_by_canonical_id(
            first.canonical_id
        )["display_name"]
        == "Equipo Original"
    )
    assert rename.previous_event_id == alias.event_id


def test_supersession_is_bitemporal_and_does_not_rewrite_history(
    tmp_path,
):
    (
        registry,
        ledger,
        first,
        second,
        _,
    ) = prepared(
        tmp_path
    )

    event = append_football_identity_supersession(
        ledger=ledger,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=(
            second.canonical_id
        ),
        entity_type="team",
        effective_at=at(3),
        known_at=at(4),
        reason_code="DUPLICATE_CANONICAL_IDENTITY",
        previous_event_id=None,
        human_reviewed=True,
    )

    assert (
        ledger.resolve_terminal_canonical_id_as_of(
            canonical_id=first.canonical_id,
            as_of=at(3),
            event_time=at(3),
        )
        == first.canonical_id
    )

    assert (
        ledger.resolve_terminal_canonical_id_as_of(
            canonical_id=first.canonical_id,
            as_of=at(4),
            event_time=at(3),
        )
        == second.canonical_id
    )

    assert (
        registry.get_by_canonical_id(
            first.canonical_id
        )["canonical_id"]
        == first.canonical_id
    )
    assert (
        registry.get_by_canonical_id(
            second.canonical_id
        )["canonical_id"]
        == second.canonical_id
    )
    assert event.human_reviewed is True


def test_supersession_requires_human_review(
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

    with pytest.raises(
        ValueError,
        match=(
            "IDENTITY_SUPERSESSION_REQUIRES_HUMAN_REVIEW"
        ),
    ):
        ledger.build_event(
            sport="football",
            entity_type="team",
            canonical_id=first.canonical_id,
            event_type="SUPERSEDED",
            effective_at=at(2),
            known_at=at(2),
            reason_code="MERGE",
            human_reviewed=False,
            superseded_by_canonical_id=(
                second.canonical_id
            ),
        )


def test_supersession_rejects_cross_sport_target(
    tmp_path,
):
    (
        _,
        ledger,
        first,
        _,
        tennis,
    ) = prepared(
        tmp_path
    )

    event = ledger.build_event(
        sport="football",
        entity_type="team",
        canonical_id=first.canonical_id,
        event_type="SUPERSEDED",
        effective_at=at(2),
        known_at=at(2),
        reason_code="INVALID_TARGET_TEST",
        human_reviewed=True,
        superseded_by_canonical_id=(
            tennis.canonical_id
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "IDENTITY_SUPERSESSION_SCOPE_MISMATCH"
        ),
    ):
        ledger.append(
            event
        )


def test_superseded_identity_is_terminal(
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

    supersession = (
        append_football_identity_supersession(
            ledger=ledger,
            canonical_id=first.canonical_id,
            superseded_by_canonical_id=(
                second.canonical_id
            ),
            entity_type="team",
            effective_at=at(2),
            known_at=at(2),
            reason_code="MERGE",
            previous_event_id=None,
            human_reviewed=True,
        )
    )

    later = ledger.build_event(
        sport="football",
        entity_type="team",
        canonical_id=first.canonical_id,
        event_type="ALIAS_ADDED",
        effective_at=at(3),
        known_at=at(3),
        reason_code="LATE_ALIAS",
        human_reviewed=False,
        previous_event_id=(
            supersession.event_id
        ),
        alias="Should Fail",
    )

    with pytest.raises(
        ValueError,
        match="SUPERSEDED_IDENTITY_IS_TERMINAL",
    ):
        ledger.append(
            later
        )


def test_lifecycle_has_no_name_resolution_api(
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
        "get_by_alias",
    )
    assert not hasattr(
        ledger,
        "resolve_by_name",
    )
    assert not hasattr(
        ledger,
        "find_by_name",
    )


def test_tennis_adapter_cannot_append_to_football_identity(
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
            "IDENTITY_LIFECYCLE_CANONICAL_BINDING_MISMATCH"
        ),
    ):
        append_tennis_identity_alias(
            ledger=ledger,
            canonical_id=first.canonical_id,
            entity_type="player",
            alias="Cross Sport",
            effective_at=at(1),
            known_at=at(1),
            reason_code="INVALID",
        )


def test_lifecycle_tampering_is_detected(
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

    event = append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Alias",
        effective_at=at(1),
        known_at=at(1),
        reason_code="VERIFIED_ALIAS",
    )

    with sqlite3.connect(
        ledger.path
    ) as connection:
        connection.execute(
            "UPDATE canonical_identity_lifecycle "
            "SET payload_json = ? WHERE event_id = ?",
            (
                '{"tampered":true}\n',
                event.event_id,
            ),
        )
        connection.commit()

    assert (
        ledger.audit_integrity().ok
        is False
    )


def test_lifecycle_safety_flags_are_false(
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

    event = append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Alias",
        effective_at=at(1),
        known_at=at(1),
        reason_code="VERIFIED_ALIAS",
    )

    payload = event.payload()

    assert payload["name_join_allowed"] is False
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False


def test_staggered_effective_supersession_cycle_is_rejected_at_append(
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

    append_football_identity_supersession(
        ledger=ledger,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="team",
        effective_at=at(10),
        known_at=at(12),
        reason_code="A_TO_B",
        previous_event_id=None,
        human_reviewed=True,
    )

    with pytest.raises(
        ValueError,
        match="IDENTITY_SUPERSESSION_CYCLE",
    ):
        append_football_identity_supersession(
            ledger=ledger,
            canonical_id=second.canonical_id,
            superseded_by_canonical_id=first.canonical_id,
            entity_type="team",
            effective_at=at(5),
            known_at=at(13),
            reason_code="B_TO_A_RETROACTIVE",
            previous_event_id=None,
            human_reviewed=True,
        )
