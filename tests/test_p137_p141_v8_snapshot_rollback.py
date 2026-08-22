import sqlite3
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.freshness_root import InMemoryFreshnessRoot

from app.application.football.identity_lifecycle import (
    append_football_identity_alias,
    append_football_identity_supersession,
    append_football_temporal_provider_binding,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_identity_lifecycle import (
    SQLiteCanonicalIdentityLifecycleLedger,
)
from app.core.provider_identity_lifecycle import (
    SQLiteTemporalProviderIdentityLedger,
)


BASE = datetime(2026, 8, 21, tzinfo=timezone.utc)


def at(hours: int):
    return BASE + timedelta(hours=hours)


def build_registry(tmp_path, prefix):
    registry = SQLiteCanonicalIdentityRegistry(
        tmp_path / f"{prefix.lower()}-registry.db"
    )

    entities = []

    for suffix in ("A", "B"):
        entity = registry.build_entity(
            sport="football",
            entity_type="team",
            canonical_key=f"TEAM:F:{prefix}:{suffix}",
            display_name=f"{prefix} Team {suffix}",
        )
        registry.register(entity)
        entities.append(entity)

    return registry, entities


def test_v8_old_consistent_canonical_snapshot_cannot_be_replayed(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8ROLLBACKCANONICAL",
    )
    first, second = entities

    path = tmp_path / "canonical.db"
    old_snapshot = tmp_path / "canonical-old.db"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    # Preserve a legitimate older, internally consistent database.
    shutil.copy2(path, old_snapshot)

    append_football_identity_supersession(
        ledger=ledger,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="team",
        effective_at=at(10),
        known_at=at(12),
        reason_code="V8_ADVANCE_CANONICAL_HISTORY",
        previous_event_id=None,
        human_reviewed=True,
    )

    assert (
        ledger.resolve_terminal_canonical_id_as_of(
            canonical_id=first.canonical_id,
            as_of=at(12),
            event_time=at(10),
        )
        == second.canonical_id
    )

    assert ledger.audit_integrity().ok is True

    # Restore the older complete SQLite state while external evidence
    # remains at the newer trusted state.
    shutil.copy2(old_snapshot, path)

    # Required invariant:
    # silently accepting an older consistent database is forbidden.
    with pytest.raises(ValueError):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
        )


def test_v8_old_consistent_provider_snapshot_cannot_be_replayed(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8ROLLBACKPROVIDER",
    )
    first, second = entities

    path = tmp_path / "provider.db"
    old_snapshot = tmp_path / "provider-old.db"

    ledger = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    append_football_temporal_provider_binding(
        ledger=ledger,
        entity_type="team",
        provider_key="provider-v8",
        provider_entity_id="team-snapshot",
        canonical_id=first.canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="V8_INITIAL_PROVIDER_BINDING",
        human_reviewed=False,
    )

    assert ledger.audit_integrity().ok is True

    # Preserve the legitimate older state.
    shutil.copy2(path, old_snapshot)

    _, successor = ledger.remap(
        sport="football",
        entity_type="team",
        provider_key="provider-v8",
        provider_entity_id="team-snapshot",
        new_canonical_id=second.canonical_id,
        remap_at=at(10),
        known_at=at(12),
        resolution_method="manual_verified",
        reason_code="V8_ADVANCE_PROVIDER_HISTORY",
        human_reviewed=True,
    )

    assert successor.canonical_id == second.canonical_id
    assert ledger.audit_integrity().ok is True

    # Restore the complete older SQLite state.
    shutil.copy2(old_snapshot, path)

    # Required invariant:
    # the rollback must be detected despite internal consistency.
    with pytest.raises(ValueError):
        SQLiteTemporalProviderIdentityLedger(
            path,
            identity_registry=registry,
        )
def canonical_checkpoint(path: Path):
    return Path(
        str(path.resolve())
        + ".canonical_identity_lifecycle_tail_guard.tail-checkpoint"
    )


def provider_checkpoint(path: Path):
    return Path(
        str(path.resolve())
        + ".temporal_provider_identity_tail_guard.tail-checkpoint"
    )


def test_v8_canonical_missing_tail_checkpoint_fails_closed(
    tmp_path,
):
    registry, _ = build_registry(
        tmp_path,
        "V8MISSCPCANONICAL",
    )

    path = tmp_path / "canonical-missing-checkpoint.db"

    SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    checkpoint = canonical_checkpoint(
        path
    )

    assert checkpoint.exists()

    checkpoint.unlink()

    with pytest.raises(
        ValueError,
        match=(
            "APPEND_ONLY_TAIL_GUARD_"
            "EXTERNAL_CHECKPOINT_REQUIRED"
        ),
    ):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
        )


def test_v8_provider_missing_tail_checkpoint_fails_closed(
    tmp_path,
):
    registry, _ = build_registry(
        tmp_path,
        "V8MISSCPPROVIDER",
    )

    path = tmp_path / "provider-missing-checkpoint.db"

    SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    checkpoint = provider_checkpoint(
        path
    )

    assert checkpoint.exists()

    checkpoint.unlink()

    with pytest.raises(
        ValueError,
        match=(
            "APPEND_ONLY_TAIL_GUARD_"
            "EXTERNAL_CHECKPOINT_REQUIRED"
        ),
    ):
        SQLiteTemporalProviderIdentityLedger(
            path,
            identity_registry=registry,
        )


def test_v8_canonical_checkpoint_can_recover_forward_only(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8FORWARDCANONICAL",
    )
    first, second = entities

    path = tmp_path / "canonical-forward-recovery.db"
    stale_checkpoint = tmp_path / "canonical-stale-checkpoint"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    checkpoint = canonical_checkpoint(
        path
    )

    assert checkpoint.exists()

    shutil.copy2(
        checkpoint,
        stale_checkpoint,
    )

    append_football_identity_supersession(
        ledger=ledger,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="team",
        effective_at=at(10),
        known_at=at(12),
        reason_code="V8_FORWARD_CANONICAL",
        previous_event_id=None,
        human_reviewed=True,
    )

    current_checkpoint_text = (
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    shutil.copy2(
        stale_checkpoint,
        checkpoint,
    )

    assert (
        checkpoint.read_text(
            encoding="utf-8"
        )
        != current_checkpoint_text
    )

    reopened = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
    )

    assert (
        reopened.resolve_terminal_canonical_id_as_of(
            canonical_id=first.canonical_id,
            as_of=at(12),
            event_time=at(10),
        )
        == second.canonical_id
    )

    assert reopened.audit_integrity().ok is True

    assert (
        checkpoint.read_text(
            encoding="utf-8"
        )
        == current_checkpoint_text
    )


def test_v8_provider_checkpoint_can_recover_forward_only(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8FORWARDPROVIDER",
    )
    first, second = entities

    path = tmp_path / "provider-forward-recovery.db"
    stale_checkpoint = tmp_path / "provider-stale-checkpoint"

    ledger = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    append_football_temporal_provider_binding(
        ledger=ledger,
        entity_type="team",
        provider_key="provider-v8-forward",
        provider_entity_id="team-forward",
        canonical_id=first.canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="V8_FORWARD_INITIAL",
        human_reviewed=False,
    )

    checkpoint = provider_checkpoint(
        path
    )

    assert checkpoint.exists()

    shutil.copy2(
        checkpoint,
        stale_checkpoint,
    )

    ledger.remap(
        sport="football",
        entity_type="team",
        provider_key="provider-v8-forward",
        provider_entity_id="team-forward",
        new_canonical_id=second.canonical_id,
        remap_at=at(10),
        known_at=at(12),
        resolution_method="manual_verified",
        reason_code="V8_FORWARD_REMAP",
        human_reviewed=True,
    )

    current_checkpoint_text = (
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    shutil.copy2(
        stale_checkpoint,
        checkpoint,
    )

    assert (
        checkpoint.read_text(
            encoding="utf-8"
        )
        != current_checkpoint_text
    )

    reopened = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
    )

    resolved = reopened.resolve_as_of(
        sport="football",
        entity_type="team",
        provider_key="provider-v8-forward",
        provider_entity_id="team-forward",
        as_of=at(12),
        event_time=at(10),
    )

    assert resolved is not None
    assert resolved.canonical_id == second.canonical_id
    assert reopened.audit_integrity().ok is True

    assert (
        checkpoint.read_text(
            encoding="utf-8"
        )
        == current_checkpoint_text
    )
def v8_make_sqlite_snapshot(
    source_path,
    snapshot_path,
):
    with sqlite3.connect(source_path) as source:
        with sqlite3.connect(snapshot_path) as destination:
            source.backup(destination)
            destination.commit()


def v8_restore_sqlite_snapshot(
    snapshot_path,
    target_path,
):
    with sqlite3.connect(snapshot_path) as source:
        with sqlite3.connect(target_path) as destination:
            source.backup(destination)
            destination.commit()


def test_v8_paired_canonical_snapshot_rollback_requires_independent_freshness_root(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8PAIREDCANONICAL",
    )
    first, second = entities

    freshness_root = InMemoryFreshnessRoot()

    path = tmp_path / "paired-canonical.db"
    old_snapshot = tmp_path / "paired-canonical-old.db"
    old_checkpoint = tmp_path / "paired-canonical-old.checkpoint"

    ledger = SQLiteCanonicalIdentityLifecycleLedger(
        path,
        identity_registry=registry,
        freshness_root=freshness_root,
        freshness_scope_id="v8-paired-canonical-scope",
    )

    append_football_identity_alias(
        ledger=ledger,
        canonical_id=first.canonical_id,
        entity_type="team",
        alias="OLD STATE",
        effective_at=at(1),
        known_at=at(1),
        reason_code="V8_PAIRED_CANONICAL_OLD",
    )

    assert ledger.audit_integrity().ok is True

    v8_make_sqlite_snapshot(
        path,
        old_snapshot,
    )

    shutil.copy2(
        canonical_checkpoint(path),
        old_checkpoint,
    )

    append_football_identity_alias(
        ledger=ledger,
        canonical_id=second.canonical_id,
        entity_type="team",
        alias="NEW STATE",
        effective_at=at(2),
        known_at=at(2),
        reason_code="V8_PAIRED_CANONICAL_NEW",
    )

    assert ledger.audit_integrity().ok is True

    v8_restore_sqlite_snapshot(
        old_snapshot,
        path,
    )

    shutil.copy2(
        old_checkpoint,
        canonical_checkpoint(path),
    )

    with pytest.raises(ValueError):
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=registry,
            freshness_root=freshness_root,
            freshness_scope_id="v8-paired-canonical-scope",
        )


def test_v8_paired_provider_snapshot_rollback_requires_independent_freshness_root(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "V8PAIREDPROVIDER",
    )
    first, second = entities

    freshness_root = InMemoryFreshnessRoot()

    path = tmp_path / "paired-provider.db"
    old_snapshot = tmp_path / "paired-provider-old.db"
    old_checkpoint = tmp_path / "paired-provider-old.checkpoint"

    ledger = SQLiteTemporalProviderIdentityLedger(
        path,
        identity_registry=registry,
        freshness_root=freshness_root,
        freshness_scope_id="v8-paired-provider-scope",
    )

    append_football_temporal_provider_binding(
        ledger=ledger,
        entity_type="team",
        provider_key="provider-v8-paired",
        provider_entity_id="team-paired",
        canonical_id=first.canonical_id,
        valid_from=at(1),
        valid_to=None,
        known_at=at(1),
        resolution_method="provider_stable_id",
        reason_code="V8_PAIRED_PROVIDER_OLD",
        human_reviewed=False,
    )

    assert ledger.audit_integrity().ok is True

    v8_make_sqlite_snapshot(
        path,
        old_snapshot,
    )

    shutil.copy2(
        provider_checkpoint(path),
        old_checkpoint,
    )

    ledger.remap(
        sport="football",
        entity_type="team",
        provider_key="provider-v8-paired",
        provider_entity_id="team-paired",
        new_canonical_id=second.canonical_id,
        remap_at=at(10),
        known_at=at(12),
        resolution_method="manual_verified",
        reason_code="V8_PAIRED_PROVIDER_NEW",
        human_reviewed=True,
    )

    assert ledger.audit_integrity().ok is True

    v8_restore_sqlite_snapshot(
        old_snapshot,
        path,
    )

    shutil.copy2(
        old_checkpoint,
        provider_checkpoint(path),
    )

    with pytest.raises(ValueError):
        SQLiteTemporalProviderIdentityLedger(
            path,
            identity_registry=registry,
            freshness_root=freshness_root,
            freshness_scope_id="v8-paired-provider-scope",
        )
