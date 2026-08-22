import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.application.football.identity_lifecycle import (
    append_football_identity_alias,
    append_football_temporal_provider_binding,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.canonical_identity_lifecycle import (
    SQLiteCanonicalIdentityLifecycleLedger,
)
from app.core.freshness_root import (
    FreshnessState,
    InMemoryFreshnessRoot,
)
from app.core.provider_identity_lifecycle import (
    SQLiteTemporalProviderIdentityLedger,
)


BASE = datetime(
    2026,
    8,
    21,
    tzinfo=timezone.utc,
)


def at(hours):
    return BASE + timedelta(
        hours=hours
    )


def build_registry(
    tmp_path,
    prefix,
):
    store = SQLiteCanonicalIdentityRegistry(
        tmp_path
        / f"{prefix.lower()}-registry.db"
    )

    entities = []

    for suffix in (
        "A",
        "B",
    ):
        entity = store.build_entity(
            sport="football",
            entity_type="team",
            canonical_key=(
                f"TEAM:F:{prefix}:{suffix}"
            ),
            display_name=(
                f"{prefix} Team {suffix}"
            ),
        )

        store.register(
            entity
        )

        entities.append(
            entity
        )

    return store, entities


def raw_count(
    path,
    table,
):
    with sqlite3.connect(
        path
    ) as connection:
        return int(
            connection.execute(
                f"SELECT COUNT(*) "
                f"FROM {table}"
            ).fetchone()[0]
        )


def tail_tip(
    path,
    table,
):
    with sqlite3.connect(
        path
    ) as connection:
        row = connection.execute(
            f"SELECT "
            f"sequence_id, "
            f"commitment_sha256 "
            f"FROM {table} "
            f"ORDER BY sequence_id DESC "
            f"LIMIT 1"
        ).fetchone()

    if row is None:
        return (
            0,
            None,
        )

    return (
        int(row[0]),
        str(row[1]),
    )


def checkpoint_path(
    path,
    guard_table,
):
    return Path(
        str(
            Path(path).resolve()
        )
        + "."
        + guard_table
        + ".tail-checkpoint"
    )


def reserve_competing_transition(
    *,
    ledger,
    root,
    sequence_delta,
    commitment_character,
    transaction_id,
):
    namespace = (
        ledger._tail_guard
        .freshness_namespace
    )

    expected = root.read(
        namespace
    )

    assert expected is not None

    intended = FreshnessState(
        namespace=namespace,
        sequence_id=(
            expected.sequence_id
            + sequence_delta
        ),
        commitment_sha256=(
            commitment_character
            * 64
        ),
    )

    assert root.prepare(
        namespace=namespace,
        expected=expected,
        intended=intended,
        transaction_id=transaction_id,
    )

    pending = root.read_pending(
        namespace
    )

    assert pending is not None
    assert (
        pending.transaction_id
        == transaction_id
    )

    return (
        namespace,
        expected,
        pending,
    )


def test_canonical_competing_reservation_rejects_before_commit(
    tmp_path,
):
    store, entities = build_registry(
        tmp_path,
        "B2FCANONICAL",
    )

    first, _ = entities

    path = (
        tmp_path
        / "canonical-b2f.db"
    )

    root = InMemoryFreshnessRoot()

    ledger = (
        SQLiteCanonicalIdentityLifecycleLedger(
            path,
            identity_registry=store,
            freshness_root=root,
            freshness_scope_id=(
                "v8-b2f-canonical-scope"
            ),
        )
    )

    guard_table = (
        "canonical_identity_lifecycle_"
        "tail_guard"
    )

    assert raw_count(
        path,
        "canonical_identity_lifecycle",
    ) == 0

    tail_before = tail_tip(
        path,
        guard_table,
    )

    checkpoint = checkpoint_path(
        path,
        guard_table,
    )

    checkpoint_before = (
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    (
        namespace,
        expected,
        pending,
    ) = reserve_competing_transition(
        ledger=ledger,
        root=root,
        sequence_delta=1,
        commitment_character="a",
        transaction_id=(
            "reserved-by-other-canonical"
        ),
    )

    with pytest.raises(
        ValueError
    ):
        append_football_identity_alias(
            ledger=ledger,
            canonical_id=(
                first.canonical_id
            ),
            entity_type="team",
            alias=(
                "B2F REJECTED CANONICAL"
            ),
            effective_at=at(1),
            known_at=at(1),
            reason_code=(
                "V8_B2F_RESERVATION_CONFLICT"
            ),
        )

    # Critical property:
    # failure must happen before durable COMMIT.
    assert raw_count(
        path,
        "canonical_identity_lifecycle",
    ) == 0

    assert tail_tip(
        path,
        guard_table,
    ) == tail_before

    assert checkpoint.read_text(
        encoding="utf-8"
    ) == checkpoint_before

    assert root.read(
        namespace
    ) == expected

    assert root.read_pending(
        namespace
    ) == pending


def test_provider_append_competing_reservation_rejects_before_commit(
    tmp_path,
):
    store, entities = build_registry(
        tmp_path,
        "B2FPROVIDERAPPEND",
    )

    first, _ = entities

    path = (
        tmp_path
        / "provider-append-b2f.db"
    )

    root = InMemoryFreshnessRoot()

    ledger = (
        SQLiteTemporalProviderIdentityLedger(
            path,
            identity_registry=store,
            freshness_root=root,
            freshness_scope_id=(
                "v8-b2f-provider-append-scope"
            ),
        )
    )

    guard_table = (
        "temporal_provider_identity_"
        "tail_guard"
    )

    assert raw_count(
        path,
        "temporal_provider_identity_binding",
    ) == 0

    tail_before = tail_tip(
        path,
        guard_table,
    )

    checkpoint = checkpoint_path(
        path,
        guard_table,
    )

    checkpoint_before = (
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    (
        namespace,
        expected,
        pending,
    ) = reserve_competing_transition(
        ledger=ledger,
        root=root,
        sequence_delta=1,
        commitment_character="b",
        transaction_id=(
            "reserved-by-other-provider-append"
        ),
    )

    with pytest.raises(
        ValueError
    ):
        append_football_temporal_provider_binding(
            ledger=ledger,
            entity_type="team",
            provider_key="provider-v8-b2f",
            provider_entity_id=(
                "team-provider-append"
            ),
            canonical_id=(
                first.canonical_id
            ),
            valid_from=at(1),
            valid_to=None,
            known_at=at(1),
            resolution_method=(
                "provider_stable_id"
            ),
            reason_code=(
                "V8_B2F_INITIAL"
            ),
            human_reviewed=False,
        )

    # Critical property:
    # a rejected reservation cannot leave the
    # provider binding durable.
    assert raw_count(
        path,
        "temporal_provider_identity_binding",
    ) == 0

    assert tail_tip(
        path,
        guard_table,
    ) == tail_before

    assert checkpoint.read_text(
        encoding="utf-8"
    ) == checkpoint_before

    assert root.read(
        namespace
    ) == expected

    assert root.read_pending(
        namespace
    ) == pending


def test_provider_remap_competing_reservation_rejects_entire_two_record_transaction(
    tmp_path,
):
    store, entities = build_registry(
        tmp_path,
        "B2FPROVIDERREMAP",
    )

    first, second = entities

    path = (
        tmp_path
        / "provider-remap-b2f.db"
    )

    root = InMemoryFreshnessRoot()

    ledger = (
        SQLiteTemporalProviderIdentityLedger(
            path,
            identity_registry=store,
            freshness_root=root,
            freshness_scope_id=(
                "v8-b2f-provider-remap-scope"
            ),
        )
    )

    initial = (
        append_football_temporal_provider_binding(
            ledger=ledger,
            entity_type="team",
            provider_key="provider-v8-b2f-remap",
            provider_entity_id=(
                "team-provider-remap"
            ),
            canonical_id=(
                first.canonical_id
            ),
            valid_from=at(1),
            valid_to=None,
            known_at=at(1),
            resolution_method=(
                "provider_stable_id"
            ),
            reason_code=(
                "V8_B2F_INITIAL"
            ),
            human_reviewed=False,
        )
    )

    assert initial is not None

    guard_table = (
        "temporal_provider_identity_"
        "tail_guard"
    )

    assert raw_count(
        path,
        "temporal_provider_identity_binding",
    ) == 1

    tail_before = tail_tip(
        path,
        guard_table,
    )

    checkpoint = checkpoint_path(
        path,
        guard_table,
    )

    checkpoint_before = (
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    (
        namespace,
        expected,
        pending,
    ) = reserve_competing_transition(
        ledger=ledger,
        root=root,
        sequence_delta=2,
        commitment_character="c",
        transaction_id=(
            "reserved-by-other-provider-remap"
        ),
    )

    with pytest.raises(
        ValueError
    ):
        ledger.remap(
            sport="football",
            entity_type="team",
            provider_key=(
                "provider-v8-b2f-remap"
            ),
            provider_entity_id=(
                "team-provider-remap"
            ),
            new_canonical_id=(
                second.canonical_id
            ),
            remap_at=at(10),
            known_at=at(12),
            resolution_method=(
                "manual_verified"
            ),
            reason_code=(
                "V8_B2F_REMAP"
            ),
            human_reviewed=True,
        )

    # Remap creates two lifecycle transitions.
    # On reservation loss, neither may survive.
    assert raw_count(
        path,
        "temporal_provider_identity_binding",
    ) == 1

    assert tail_tip(
        path,
        guard_table,
    ) == tail_before

    assert checkpoint.read_text(
        encoding="utf-8"
    ) == checkpoint_before

    assert root.read(
        namespace
    ) == expected

    assert root.read_pending(
        namespace
    ) == pending
