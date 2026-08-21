import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.application.football.identity_lifecycle import (
    append_football_identity_alias,
    append_football_identity_supersession,
    append_football_temporal_provider_binding,
)
from app.core.canonical_identity import SQLiteCanonicalIdentityRegistry
from app.core.canonical_identity_lifecycle import (
    SQLiteCanonicalIdentityLifecycleLedger,
)
from app.core.provider_identity_lifecycle import (
    SQLiteTemporalProviderIdentityLedger,
)


BASE = datetime(2026, 8, 21, tzinfo=timezone.utc)


def at(hours: int):
    return BASE + timedelta(hours=hours)


def build_registry(tmp_path, prefix="V8"):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / f"{prefix.lower()}-registry.db"
    )

    entities = []

    for suffix in ("A", "B", "C", "D"):
        entity = registry.build_entity(
            sport="football",
            entity_type="team",
            canonical_key=f"TEAM:F:{prefix}:{suffix}",
            display_name=f"{prefix} Team {suffix}",
        )
        registry.register(entity)
        entities.append(entity)

    return registry, entities


def canonical_anchor(path: Path):
    return Path(
        str(path.resolve())
        + ".canonical_identity_lifecycle_tail_guard.init-anchor"
    )


def remove_sqlite_files(path: Path):
    for candidate in (
        path,
        Path(str(path) + "-wal"),
        Path(str(path) + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


def test_v8_external_anchor_tamper_blocks_reopen(tmp_path):
    registry, entities = build_registry(tmp_path, "ANCHORTAMPER")
    first = entities[0]

    path = tmp_path / "anchor-tamper.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Anchor Alias",
        effective_at=at(1),
        known_at=at(1),
        reason_code="V8_ANCHOR_TAMPER",
    )

    anchor = canonical_anchor(path)

    assert anchor.exists()

    anchor.write_text(
        "V8-DELIBERATELY-TAMPERED-ANCHOR",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID",
    ):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
        )


def test_v8_established_ledger_missing_external_anchor_fails_closed(
    tmp_path,
):
    registry, entities = build_registry(tmp_path, "ANCHORMISSING")
    first = entities[0]

    path = tmp_path / "anchor-missing.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Established Alias",
        effective_at=at(1),
        known_at=at(1),
        reason_code="V8_ANCHOR_DELETE",
    )

    anchor = canonical_anchor(path)

    assert anchor.exists()

    anchor.unlink()

    with pytest.raises(
        ValueError,
        match="APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED",
    ):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
        )


def test_v8_whole_database_deletion_cannot_rebaseline(tmp_path):
    registry, entities = build_registry(tmp_path, "DBDELETE")
    first = entities[0]

    path = tmp_path / "whole-db-delete.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="Historical Alias",
        effective_at=at(1),
        known_at=at(1),
        reason_code="V8_DATABASE_DELETE",
    )

    anchor = canonical_anchor(path)

    assert anchor.exists()
    assert path.exists()

    remove_sqlite_files(path)

    assert not path.exists()
    assert anchor.exists()

    with pytest.raises(
        ValueError,
        match="APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN",
    ):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
        )


def test_v8_three_node_supersession_cycle_is_rejected(tmp_path):
    registry, entities = build_registry(tmp_path, "THREECYCLE")
    first, second, third, _ = entities

    path = tmp_path / "three-cycle.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    append_football_identity_supersession(
        ledger=ledger,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="team",
        effective_at=at(10),
        known_at=at(11),
        reason_code="V8_A_TO_B",
        previous_event_id=None,
        human_reviewed=True,
    )

    append_football_identity_supersession(
        ledger=ledger,
        canonical_id=second.canonical_id,
        superseded_by_canonical_id=third.canonical_id,
        entity_type="team",
        effective_at=at(20),
        known_at=at(21),
        reason_code="V8_B_TO_C",
        previous_event_id=None,
        human_reviewed=True,
    )

    with pytest.raises(
        ValueError,
        match="IDENTITY_SUPERSESSION",
    ):
        append_football_identity_supersession(
            ledger=ledger,
            canonical_id=third.canonical_id,
            superseded_by_canonical_id=first.canonical_id,
            entity_type="team",
            effective_at=at(30),
            known_at=at(31),
            reason_code="V8_C_TO_A",
            previous_event_id=None,
            human_reviewed=True,
        )

    assert ledger.audit_integrity().ok is True


def test_v8_canonical_tail_guard_failure_rolls_back_primary_insert(
    tmp_path,
):
    registry, entities = build_registry(tmp_path, "CANONROLLBACK")
    first = entities[0]

    path = tmp_path / "canonical-rollback.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER v8_fail_canonical_tail_guard
            BEFORE INSERT ON canonical_identity_lifecycle_tail_guard
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'V8_INJECTED_CANONICAL_FAILURE'
                );
            END
            """
        )
        connection.commit()

    with pytest.raises(sqlite3.DatabaseError):
        append_football_identity_alias(
            ledger=ledger,
            canonical_id=first.canonical_id,
            entity_type="team",
            alias="Must Roll Back",
            effective_at=at(1),
            known_at=at(1),
            reason_code="V8_CANONICAL_ROLLBACK",
        )

    with sqlite3.connect(path) as connection:
        connection.execute(
            "DROP TRIGGER v8_fail_canonical_tail_guard"
        )
        connection.commit()

        lifecycle_count = connection.execute(
            "SELECT COUNT(*) FROM canonical_identity_lifecycle"
        ).fetchone()[0]

        guard_count = connection.execute(
            "SELECT COUNT(*) "
            "FROM canonical_identity_lifecycle_tail_guard"
        ).fetchone()[0]

    assert lifecycle_count == 0
    assert guard_count == 0

    reopened = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    assert reopened.audit_integrity().ok is True


def test_v8_provider_remap_failure_rolls_back_entire_transaction(
    tmp_path,
):
    registry, entities = build_registry(tmp_path, "PROVIDERROLLBACK")
    first, second, _, _ = entities

    path = tmp_path / "provider-rollback.db"

    ledger = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    initial = append_football_temporal_provider_binding(
        ledger=ledger,
        entity_type="team",
        provider_key="provider-v8",
        provider_entity_id="team-rollback",
        canonical_id=first.canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="V8_INITIAL",
        human_reviewed=False,
    )

    history_before = ledger.history(
        sport="football",
        entity_type="team",
        provider_key="provider-v8",
        provider_entity_id="team-rollback",
    )

    assert len(history_before) == 1
    assert history_before[0].binding_id == initial.binding_id

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER v8_fail_provider_tail_guard
            BEFORE INSERT ON temporal_provider_identity_tail_guard
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'V8_INJECTED_PROVIDER_FAILURE'
                );
            END
            """
        )
        connection.commit()

    with pytest.raises(sqlite3.DatabaseError):
        ledger.remap(
            sport="football",
            entity_type="team",
            provider_key="provider-v8",
            provider_entity_id="team-rollback",
            new_canonical_id=second.canonical_id,
            remap_at=at(10),
            known_at=at(12),
            resolution_method="manual_verified",
            reason_code="V8_FORCED_ROLLBACK",
            human_reviewed=True,
        )

    with sqlite3.connect(path) as connection:
        connection.execute(
            "DROP TRIGGER v8_fail_provider_tail_guard"
        )
        connection.commit()

    reopened = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    history_after = reopened.history(
        sport="football",
        entity_type="team",
        provider_key="provider-v8",
        provider_entity_id="team-rollback",
    )

    assert len(history_after) == 1
    assert history_after[0].binding_id == initial.binding_id
    assert history_after[0].valid_to is None
    assert reopened.audit_integrity().ok is True
