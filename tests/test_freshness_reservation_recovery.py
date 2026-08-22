import sqlite3

import pytest

from app.core.append_only_tail_guard import (
    SQLiteAppendOnlyTailGuard,
)
from app.core.freshness_root import (
    FreshnessState,
    InMemoryFreshnessRoot,
)


TABLE = "v8_b2g_recovery_guard"
LEDGER = "v8-b2g-recovery-ledger"
SCOPE = "v8-b2g-recovery-scope"


def make_guard(root):
    return SQLiteAppendOnlyTailGuard(
        table_name=TABLE,
        ledger_name=LEDGER,
        freshness_root=root,
        freshness_scope_id=SCOPE,
    )


def open_connection(path):
    return sqlite3.connect(
        path,
        isolation_level=None,
    )


def initialize_empty(path, root):
    connection = open_connection(
        path
    )

    guard = make_guard(
        root
    )

    guard.ensure_schema(
        connection
    )

    guard.bootstrap_if_pristine(
        connection,
        records=(),
    )

    guard.initialize_or_reconcile_freshness_root(
        connection
    )

    return (
        connection,
        guard,
    )


def reopen(
    path,
    root,
    records,
):
    connection = open_connection(
        path
    )

    guard = make_guard(
        root
    )

    guard.ensure_schema(
        connection
    )

    guard.bootstrap_if_pristine(
        connection,
        records=records,
    )

    return (
        connection,
        guard,
    )


def intended_state(
    guard,
    connection,
):
    return guard._current_freshness_state(
        connection
    )


def test_pending_reservation_with_database_still_expected_fails_closed_and_is_preserved(
    tmp_path,
):
    path = (
        tmp_path
        / "pending-expected.db"
    )

    root = InMemoryFreshnessRoot()

    connection, guard = initialize_empty(
        path,
        root,
    )

    namespace = (
        guard.freshness_namespace
    )

    expected = root.read(
        namespace
    )

    assert expected is not None

    intended = FreshnessState(
        namespace=namespace,
        sequence_id=(
            expected.sequence_id
            + 1
        ),
        commitment_sha256=(
            "a" * 64
        ),
    )

    assert root.prepare(
        namespace=namespace,
        expected=expected,
        intended=intended,
        transaction_id=(
            "pending-no-local-commit"
        ),
    )

    pending_before = root.read_pending(
        namespace
    )

    assert pending_before is not None

    connection.close()

    reopened, reopened_guard = reopen(
        path,
        root,
        records=(),
    )

    try:
        with pytest.raises(
            ValueError,
            match=(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_PENDING_REVIEW"
            ),
        ):
            reopened_guard.initialize_or_reconcile_freshness_root(
                reopened
            )

        assert root.read(
            namespace
        ) == expected

        assert root.read_pending(
            namespace
        ) == pending_before

        assert (
            reopened_guard._current_freshness_state(
                reopened
            )
            == expected
        )

    finally:
        reopened.close()


def test_pending_reservation_with_database_at_exact_intended_state_finalizes_on_reopen(
    tmp_path,
):
    path = (
        tmp_path
        / "pending-intended.db"
    )

    root = InMemoryFreshnessRoot()

    connection, guard = initialize_empty(
        path,
        root,
    )

    namespace = (
        guard.freshness_namespace
    )

    expected = root.read(
        namespace
    )

    assert expected is not None

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    guard.append(
        connection,
        record_id="committed-record-001",
        record_payload_sha256=(
            "b" * 64
        ),
    )

    intended = intended_state(
        guard,
        connection,
    )

    assert intended != expected

    assert root.prepare(
        namespace=namespace,
        expected=expected,
        intended=intended,
        transaction_id=(
            "prepared-before-crash"
        ),
    )

    # Simulate:
    # PREPARE succeeded
    # SQLite COMMIT succeeded
    # process died before FINALIZE.
    connection.commit()
    connection.close()

    reopened, reopened_guard = reopen(
        path,
        root,
        records=(
            (
                "committed-record-001",
                "b" * 64,
            ),
        ),
    )

    try:
        reopened_guard.initialize_or_reconcile_freshness_root(
            reopened
        )

        assert root.read(
            namespace
        ) == intended

        assert root.read_pending(
            namespace
        ) is None

        assert (
            reopened_guard._current_freshness_state(
                reopened
            )
            == intended
        )

    finally:
        reopened.close()


def test_database_ahead_without_pending_reservation_cannot_be_auto_promoted(
    tmp_path,
):
    path = (
        tmp_path
        / "unprepared-extension.db"
    )

    root = InMemoryFreshnessRoot()

    connection, guard = initialize_empty(
        path,
        root,
    )

    namespace = (
        guard.freshness_namespace
    )

    expected = root.read(
        namespace
    )

    assert expected is not None
    assert root.read_pending(
        namespace
    ) is None

    # Deliberately emulate an unprepared local extension:
    # SQLite advances but the independent authority has no
    # reservation proving authorization for that transition.
    connection.execute(
        "BEGIN IMMEDIATE"
    )

    guard.append(
        connection,
        record_id="unprepared-record-001",
        record_payload_sha256=(
            "c" * 64
        ),
    )

    local_intended = intended_state(
        guard,
        connection,
    )

    assert local_intended != expected

    connection.commit()
    connection.close()

    assert root.read(
        namespace
    ) == expected

    assert root.read_pending(
        namespace
    ) is None

    reopened, reopened_guard = reopen(
        path,
        root,
        records=(
            (
                "unprepared-record-001",
                "c" * 64,
            ),
        ),
    )

    try:
        with pytest.raises(
            ValueError,
            match=(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_UNPREPARED_EXTENSION"
            ),
        ):
            reopened_guard.initialize_or_reconcile_freshness_root(
                reopened
            )

        # Critical anti-first-recovery-wins property:
        # reopening the local DB must NOT bless it into root.
        assert root.read(
            namespace
        ) == expected

        assert root.read_pending(
            namespace
        ) is None

        assert (
            reopened_guard._current_freshness_state(
                reopened
            )
            == local_intended
        )

    finally:
        reopened.close()
