from __future__ import annotations

import shutil
import sqlite3

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path

from threading import (
    Barrier,
    Lock,
    Thread,
)

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


CANONICAL_GUARD = (
    "canonical_identity_lifecycle_tail_guard"
)

PROVIDER_GUARD = (
    "temporal_provider_identity_tail_guard"
)


def at(hours):
    return BASE + timedelta(
        hours=hours
    )


def build_registry(
    tmp_path,
    prefix,
    count=3,
):
    registry = (
        SQLiteCanonicalIdentityRegistry(
            tmp_path
            / f"{prefix.lower()}-registry.db"
        )
    )

    entities = []

    for index in range(count):
        suffix = chr(
            ord("A") + index
        )

        entity = registry.build_entity(
            sport="football",
            entity_type="team",
            canonical_key=(
                f"TEAM:F:{prefix}:{suffix}"
            ),
            display_name=(
                f"{prefix} Team {suffix}"
            ),
        )

        registry.register(
            entity
        )

        entities.append(
            entity
        )

    return (
        registry,
        tuple(entities),
    )


def checkpoint_path(
    database,
    guard_table,
):
    return Path(
        str(
            Path(database).resolve()
        )
        + "."
        + guard_table
        + ".tail-checkpoint"
    )


def initialization_anchor_path(
    database,
    guard_table,
):
    return Path(
        str(
            Path(database).resolve()
        )
        + "."
        + guard_table
        + ".init-anchor"
    )


def clone_logical_ledger(
    source,
    target,
    guard_table,
):
    source = Path(source)
    target = Path(target)

    with sqlite3.connect(
        source
    ) as source_connection:
        with sqlite3.connect(
            target
        ) as target_connection:
            source_connection.backup(
                target_connection
            )

    source_checkpoint = checkpoint_path(
        source,
        guard_table,
    )

    target_checkpoint = checkpoint_path(
        target,
        guard_table,
    )

    source_anchor = (
        initialization_anchor_path(
            source,
            guard_table,
        )
    )

    target_anchor = (
        initialization_anchor_path(
            target,
            guard_table,
        )
    )

    assert source_checkpoint.exists()
    assert source_anchor.exists()

    shutil.copy2(
        source_checkpoint,
        target_checkpoint,
    )

    shutil.copy2(
        source_anchor,
        target_anchor,
    )


def row_count(
    database,
    table,
):
    with sqlite3.connect(
        database
    ) as connection:
        return int(
            connection.execute(
                f"SELECT COUNT(*) "
                f"FROM {table}"
            ).fetchone()[0]
        )


def tail_tip(
    database,
    guard_table,
):
    with sqlite3.connect(
        database
    ) as connection:
        row = connection.execute(
            f"SELECT "
            f"sequence_id, "
            f"commitment_sha256 "
            f"FROM {guard_table} "
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


class BarrierFreshnessRoot:
    """
    Test-only concurrency harness.

    Both lifecycle writers must reach prepare() before either
    delegate prepare is allowed to execute. This creates a real
    race from the same observed authority state.

    Production authorization remains False because the delegated
    InMemoryFreshnessRoot is test-only.
    """

    def __init__(
        self,
        delegate,
    ):
        self.delegate = delegate

        self.prepare_barrier = Barrier(
            2
        )

    @property
    def production_authorized(self):
        return (
            self.delegate
            .production_authorized
        )

    def read(
        self,
        namespace,
    ):
        return self.delegate.read(
            namespace
        )

    def initialize(
        self,
        *,
        namespace,
        state,
    ):
        return self.delegate.initialize(
            namespace=namespace,
            state=state,
        )

    def read_pending(
        self,
        namespace,
    ):
        return self.delegate.read_pending(
            namespace
        )

    def prepare(
        self,
        *,
        namespace,
        expected,
        intended,
        transaction_id,
    ):
        self.prepare_barrier.wait(
            timeout=10
        )

        return self.delegate.prepare(
            namespace=namespace,
            expected=expected,
            intended=intended,
            transaction_id=transaction_id,
        )

    def finalize(
        self,
        *,
        namespace,
        transaction_id,
        intended,
    ):
        return self.delegate.finalize(
            namespace=namespace,
            transaction_id=transaction_id,
            intended=intended,
        )

    def abort(
        self,
        *,
        namespace,
        transaction_id,
        expected,
    ):
        return self.delegate.abort(
            namespace=namespace,
            transaction_id=transaction_id,
            expected=expected,
        )

    def compare_and_set(
        self,
        *,
        namespace,
        expected,
        new,
    ):
        return self.delegate.compare_and_set(
            namespace=namespace,
            expected=expected,
            new=new,
        )


def run_concurrently(
    operation_a,
    operation_b,
):
    results = {}
    result_lock = Lock()

    def invoke(
        label,
        operation,
    ):
        try:
            value = operation()

            result = (
                "SUCCESS",
                value,
            )

        except Exception as error:
            result = (
                "ERROR",
                error,
            )

        with result_lock:
            results[label] = result

    thread_a = Thread(
        target=invoke,
        args=(
            "A",
            operation_a,
        ),
        daemon=True,
    )

    thread_b = Thread(
        target=invoke,
        args=(
            "B",
            operation_b,
        ),
        daemon=True,
    )

    thread_a.start()
    thread_b.start()

    thread_a.join(
        timeout=15
    )

    thread_b.join(
        timeout=15
    )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()

    assert set(
        results
    ) == {
        "A",
        "B",
    }

    winners = [
        label
        for label, result
        in results.items()
        if result[0]
        == "SUCCESS"
    ]

    losers = [
        label
        for label, result
        in results.items()
        if result[0]
        == "ERROR"
    ]

    assert len(winners) == 1
    assert len(losers) == 1

    loser_error = (
        results[
            losers[0]
        ][1]
    )

    assert isinstance(
        loser_error,
        ValueError,
    )

    return (
        winners[0],
        losers[0],
        results,
    )


def assert_root_matches_winner(
    *,
    root,
    namespace,
    winner_path,
    guard_table,
):
    current = root.read(
        namespace
    )

    assert current is not None

    winner_tail = tail_tip(
        winner_path,
        guard_table,
    )

    assert current.sequence_id == (
        winner_tail[0]
    )

    assert (
        current.commitment_sha256
        == winner_tail[1]
    )

    assert root.read_pending(
        namespace
    ) is None


def test_explicit_scope_isolates_two_independent_same_type_ledgers(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "B2HSCOPE",
        count=1,
    )

    entity = entities[0]

    root = InMemoryFreshnessRoot()

    path_a = (
        tmp_path
        / "scope-a.db"
    )

    path_b = (
        tmp_path
        / "scope-b.db"
    )

    ledger_a = (
        SQLiteCanonicalIdentityLifecycleLedger(
            path_a,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=(
                "independent-ledger-a"
            ),
        )
    )

    ledger_b = (
        SQLiteCanonicalIdentityLifecycleLedger(
            path_b,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=(
                "independent-ledger-b"
            ),
        )
    )

    namespace_a = (
        ledger_a
        ._tail_guard
        .freshness_namespace
    )

    namespace_b = (
        ledger_b
        ._tail_guard
        .freshness_namespace
    )

    assert namespace_a != namespace_b

    append_football_identity_alias(
        ledger=ledger_a,
        canonical_id=(
            entity.canonical_id
        ),
        entity_type="team",
        alias="B2H Scope A",
        effective_at=at(1),
        known_at=at(1),
        reason_code=(
            "V8_B2H_SCOPE_A"
        ),
    )

    append_football_identity_alias(
        ledger=ledger_b,
        canonical_id=(
            entity.canonical_id
        ),
        entity_type="team",
        alias="B2H Scope B",
        effective_at=at(2),
        known_at=at(2),
        reason_code=(
            "V8_B2H_SCOPE_B"
        ),
    )

    assert row_count(
        path_a,
        "canonical_identity_lifecycle",
    ) == 1

    assert row_count(
        path_b,
        "canonical_identity_lifecycle",
    ) == 1

    state_a = root.read(
        namespace_a
    )

    state_b = root.read(
        namespace_b
    )

    assert state_a is not None
    assert state_b is not None

    assert state_a.sequence_id == 1
    assert state_b.sequence_id == 1

    assert root.read_pending(
        namespace_a
    ) is None

    assert root.read_pending(
        namespace_b
    ) is None


def test_concurrent_canonical_forks_have_exactly_one_precommit_winner(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "B2HCANONICAL",
        count=1,
    )

    entity = entities[0]

    base_path = (
        tmp_path
        / "canonical-base.db"
    )

    branch_a_path = (
        tmp_path
        / "canonical-a.db"
    )

    branch_b_path = (
        tmp_path
        / "canonical-b.db"
    )

    delegate = (
        InMemoryFreshnessRoot()
    )

    scope = (
        "v8-b2h-canonical-shared-ledger"
    )

    SQLiteCanonicalIdentityLifecycleLedger(
        base_path,
        identity_registry=registry,
        freshness_root=delegate,
        freshness_scope_id=scope,
    )

    base_checkpoint = (
        checkpoint_path(
            base_path,
            CANONICAL_GUARD,
        ).read_text(
            encoding="utf-8"
        )
    )

    clone_logical_ledger(
        base_path,
        branch_a_path,
        CANONICAL_GUARD,
    )

    clone_logical_ledger(
        base_path,
        branch_b_path,
        CANONICAL_GUARD,
    )

    root = BarrierFreshnessRoot(
        delegate
    )

    ledger_a = (
        SQLiteCanonicalIdentityLifecycleLedger(
            branch_a_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    ledger_b = (
        SQLiteCanonicalIdentityLifecycleLedger(
            branch_b_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    assert (
        ledger_a
        ._tail_guard
        .freshness_namespace
        ==
        ledger_b
        ._tail_guard
        .freshness_namespace
    )

    namespace = (
        ledger_a
        ._tail_guard
        .freshness_namespace
    )

    winner, loser, _ = run_concurrently(
        lambda: append_football_identity_alias(
            ledger=ledger_a,
            canonical_id=(
                entity.canonical_id
            ),
            entity_type="team",
            alias="B2H Fork A",
            effective_at=at(1),
            known_at=at(1),
            reason_code=(
                "V8_B2H_FORK_A"
            ),
        ),
        lambda: append_football_identity_alias(
            ledger=ledger_b,
            canonical_id=(
                entity.canonical_id
            ),
            entity_type="team",
            alias="B2H Fork B",
            effective_at=at(1),
            known_at=at(1),
            reason_code=(
                "V8_B2H_FORK_B"
            ),
        ),
    )

    paths = {
        "A": branch_a_path,
        "B": branch_b_path,
    }

    winner_path = paths[
        winner
    ]

    loser_path = paths[
        loser
    ]

    assert row_count(
        winner_path,
        "canonical_identity_lifecycle",
    ) == 1

    assert row_count(
        loser_path,
        "canonical_identity_lifecycle",
    ) == 0

    assert tail_tip(
        winner_path,
        CANONICAL_GUARD,
    )[0] == 1

    assert tail_tip(
        loser_path,
        CANONICAL_GUARD,
    ) == (
        0,
        None,
    )

    assert (
        checkpoint_path(
            loser_path,
            CANONICAL_GUARD,
        ).read_text(
            encoding="utf-8"
        )
        == base_checkpoint
    )

    assert_root_matches_winner(
        root=delegate,
        namespace=namespace,
        winner_path=winner_path,
        guard_table=CANONICAL_GUARD,
    )


def test_concurrent_provider_append_forks_have_exactly_one_precommit_winner(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "B2HPROVIDERAPPEND",
        count=2,
    )

    first, second = entities

    base_path = (
        tmp_path
        / "provider-append-base.db"
    )

    branch_a_path = (
        tmp_path
        / "provider-append-a.db"
    )

    branch_b_path = (
        tmp_path
        / "provider-append-b.db"
    )

    delegate = (
        InMemoryFreshnessRoot()
    )

    scope = (
        "v8-b2h-provider-append-shared-ledger"
    )

    SQLiteTemporalProviderIdentityLedger(
        base_path,
        identity_registry=registry,
        freshness_root=delegate,
        freshness_scope_id=scope,
    )

    base_checkpoint = (
        checkpoint_path(
            base_path,
            PROVIDER_GUARD,
        ).read_text(
            encoding="utf-8"
        )
    )

    clone_logical_ledger(
        base_path,
        branch_a_path,
        PROVIDER_GUARD,
    )

    clone_logical_ledger(
        base_path,
        branch_b_path,
        PROVIDER_GUARD,
    )

    root = BarrierFreshnessRoot(
        delegate
    )

    ledger_a = (
        SQLiteTemporalProviderIdentityLedger(
            branch_a_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    ledger_b = (
        SQLiteTemporalProviderIdentityLedger(
            branch_b_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    namespace = (
        ledger_a
        ._tail_guard
        .freshness_namespace
    )

    assert (
        namespace
        ==
        ledger_b
        ._tail_guard
        .freshness_namespace
    )

    winner, loser, _ = run_concurrently(
        lambda: append_football_temporal_provider_binding(
            ledger=ledger_a,
            entity_type="team",
            provider_key=(
                "provider-v8-b2h"
            ),
            provider_entity_id=(
                "provider-team-b2h"
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
                "V8_B2H_PROVIDER_A"
            ),
            human_reviewed=False,
        ),
        lambda: append_football_temporal_provider_binding(
            ledger=ledger_b,
            entity_type="team",
            provider_key=(
                "provider-v8-b2h"
            ),
            provider_entity_id=(
                "provider-team-b2h"
            ),
            canonical_id=(
                second.canonical_id
            ),
            valid_from=at(1),
            valid_to=None,
            known_at=at(1),
            resolution_method=(
                "provider_stable_id"
            ),
            reason_code=(
                "V8_B2H_PROVIDER_B"
            ),
            human_reviewed=False,
        ),
    )

    paths = {
        "A": branch_a_path,
        "B": branch_b_path,
    }

    winner_path = paths[
        winner
    ]

    loser_path = paths[
        loser
    ]

    assert row_count(
        winner_path,
        "temporal_provider_identity_binding",
    ) == 1

    assert row_count(
        loser_path,
        "temporal_provider_identity_binding",
    ) == 0

    assert tail_tip(
        winner_path,
        PROVIDER_GUARD,
    )[0] == 1

    assert tail_tip(
        loser_path,
        PROVIDER_GUARD,
    ) == (
        0,
        None,
    )

    assert (
        checkpoint_path(
            loser_path,
            PROVIDER_GUARD,
        ).read_text(
            encoding="utf-8"
        )
        == base_checkpoint
    )

    assert_root_matches_winner(
        root=delegate,
        namespace=namespace,
        winner_path=winner_path,
        guard_table=PROVIDER_GUARD,
    )


def test_concurrent_provider_remap_forks_have_exactly_one_two_record_winner(
    tmp_path,
):
    registry, entities = build_registry(
        tmp_path,
        "B2HPROVIDERREMAP",
        count=3,
    )

    original, target_a, target_b = (
        entities
    )

    base_path = (
        tmp_path
        / "provider-remap-base.db"
    )

    branch_a_path = (
        tmp_path
        / "provider-remap-a.db"
    )

    branch_b_path = (
        tmp_path
        / "provider-remap-b.db"
    )

    delegate = (
        InMemoryFreshnessRoot()
    )

    scope = (
        "v8-b2h-provider-remap-shared-ledger"
    )

    base_ledger = (
        SQLiteTemporalProviderIdentityLedger(
            base_path,
            identity_registry=registry,
            freshness_root=delegate,
            freshness_scope_id=scope,
        )
    )

    initial = (
        append_football_temporal_provider_binding(
            ledger=base_ledger,
            entity_type="team",
            provider_key=(
                "provider-v8-b2h-remap"
            ),
            provider_entity_id=(
                "provider-team-b2h-remap"
            ),
            canonical_id=(
                original.canonical_id
            ),
            valid_from=at(1),
            valid_to=None,
            known_at=at(1),
            resolution_method=(
                "provider_stable_id"
            ),
            reason_code=(
                "V8_B2H_INITIAL"
            ),
            human_reviewed=False,
        )
    )

    assert initial is not None

    base_tail = tail_tip(
        base_path,
        PROVIDER_GUARD,
    )

    assert base_tail[0] == 1

    base_checkpoint = (
        checkpoint_path(
            base_path,
            PROVIDER_GUARD,
        ).read_text(
            encoding="utf-8"
        )
    )

    clone_logical_ledger(
        base_path,
        branch_a_path,
        PROVIDER_GUARD,
    )

    clone_logical_ledger(
        base_path,
        branch_b_path,
        PROVIDER_GUARD,
    )

    root = BarrierFreshnessRoot(
        delegate
    )

    ledger_a = (
        SQLiteTemporalProviderIdentityLedger(
            branch_a_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    ledger_b = (
        SQLiteTemporalProviderIdentityLedger(
            branch_b_path,
            identity_registry=registry,
            freshness_root=root,
            freshness_scope_id=scope,
        )
    )

    namespace = (
        ledger_a
        ._tail_guard
        .freshness_namespace
    )

    winner, loser, _ = run_concurrently(
        lambda: ledger_a.remap(
            sport="football",
            entity_type="team",
            provider_key=(
                "provider-v8-b2h-remap"
            ),
            provider_entity_id=(
                "provider-team-b2h-remap"
            ),
            new_canonical_id=(
                target_a.canonical_id
            ),
            remap_at=at(10),
            known_at=at(12),
            resolution_method=(
                "manual_verified"
            ),
            reason_code=(
                "V8_B2H_REMAP_A"
            ),
            human_reviewed=True,
        ),
        lambda: ledger_b.remap(
            sport="football",
            entity_type="team",
            provider_key=(
                "provider-v8-b2h-remap"
            ),
            provider_entity_id=(
                "provider-team-b2h-remap"
            ),
            new_canonical_id=(
                target_b.canonical_id
            ),
            remap_at=at(10),
            known_at=at(12),
            resolution_method=(
                "manual_verified"
            ),
            reason_code=(
                "V8_B2H_REMAP_B"
            ),
            human_reviewed=True,
        ),
    )

    paths = {
        "A": branch_a_path,
        "B": branch_b_path,
    }

    winner_path = paths[
        winner
    ]

    loser_path = paths[
        loser
    ]

    # Initial record + close + successor.
    assert row_count(
        winner_path,
        "temporal_provider_identity_binding",
    ) == 3

    # Loser must remain exactly at original base state.
    assert row_count(
        loser_path,
        "temporal_provider_identity_binding",
    ) == 1

    assert tail_tip(
        winner_path,
        PROVIDER_GUARD,
    )[0] == 3

    assert tail_tip(
        loser_path,
        PROVIDER_GUARD,
    ) == base_tail

    assert (
        checkpoint_path(
            loser_path,
            PROVIDER_GUARD,
        ).read_text(
            encoding="utf-8"
        )
        == base_checkpoint
    )

    assert_root_matches_winner(
        root=delegate,
        namespace=namespace,
        winner_path=winner_path,
        guard_table=PROVIDER_GUARD,
    )
