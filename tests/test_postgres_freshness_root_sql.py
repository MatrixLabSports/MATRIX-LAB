from __future__ import annotations

import copy
from threading import (
    Barrier,
    RLock,
    Thread,
)

import pytest

from app.core.freshness_root import (
    FreshnessState,
)
from app.core.postgres_freshness_root import (
    PostgresFreshnessRoot,
)
from app.security.secrets import (
    EnvironmentSecretRef,
)


SECRET_ENV = (
    "MATRIX_POSTGRES_FRESHNESS_DSN_SECRET"
)

TEST_DSN = (
    "postgresql://matrix_test:"
    "very-long-test-password@"
    "db.example.test:5432/"
    "matrix_freshness?"
    "sslmode=verify-full"
)

NAMESPACE = (
    "matrix/test/postgres/freshness"
)


def state(
    sequence_id,
    character=None,
):
    if sequence_id == 0:
        commitment = None
    else:
        assert character is not None
        commitment = (
            character * 64
        )

    return FreshnessState(
        namespace=NAMESPACE,
        sequence_id=sequence_id,
        commitment_sha256=commitment,
    )


GENESIS = state(0)
STATE_A = state(1, "a")
STATE_B = state(1, "b")
STATE_C = state(2, "c")


class ControlledCursor:
    def __init__(
        self,
        *,
        row=None,
        rowcount=0,
    ):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class ControlledPostgresStore:
    """
    Deterministic PostgreSQL-like authority for adapter tests.

    This does not implement FreshnessRoot semantics for the
    adapter. It only supplies transactional SQL primitives:
    shared durable rows, commit/rollback and row-lock-like
    serialization between connections.
    """

    def __init__(self):
        self.rows = {}
        self.lock = RLock()
        self.sql_log = []

        self.connect_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

        self.fail_fragment = None

    def connect(
        self,
        dsn,
    ):
        assert dsn == TEST_DSN

        self.connect_count += 1

        return ControlledConnection(
            self
        )


class ControlledConnection:
    def __init__(
        self,
        store,
    ):
        self.store = store

        self._locked = False
        self._working_rows = None
        self._closed = False

    def _begin_locked(
        self,
    ):
        if self._locked:
            return

        self.store.lock.acquire()

        self._locked = True

        self._working_rows = copy.deepcopy(
            self.store.rows
        )

    def _rows(
        self,
    ):
        if self._locked:
            return self._working_rows

        return self.store.rows

    @staticmethod
    def _normalize(
        sql,
    ):
        return " ".join(
            str(sql).split()
        ).upper()

    def execute(
        self,
        sql,
        params=None,
    ):
        normalized = self._normalize(
            sql
        )

        params = tuple(
            ()
            if params is None
            else params
        )

        self.store.sql_log.append(
            (
                normalized,
                params,
            )
        )

        fragment = (
            self.store.fail_fragment
        )

        if (
            fragment is not None
            and fragment.upper()
            in normalized
        ):
            raise RuntimeError(
                "controlled postgres driver failure"
            )

        if (
            "FROM MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT_SCHEMA"
            in normalized
            and "SELECT" in normalized
        ):
            return ControlledCursor(
                row=(
                    1,
                    "matrix.postgres-freshness-root/1",
                )
            )

        if (
            "FROM MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
            in normalized
            and "SELECT" in normalized
        ):
            if "FOR UPDATE" in normalized:
                self._begin_locked()

            namespace = params[0]

            row = self._rows().get(
                namespace
            )

            if row is None:
                return ControlledCursor(
                    row=None
                )

            return ControlledCursor(
                row=(
                    row[
                        "current_sequence_id"
                    ],
                    row[
                        "current_commitment_sha256"
                    ],
                    row[
                        "pending_transaction_id"
                    ],
                    row[
                        "pending_expected_sequence_id"
                    ],
                    row[
                        "pending_expected_commitment_sha256"
                    ],
                    row[
                        "pending_intended_sequence_id"
                    ],
                    row[
                        "pending_intended_commitment_sha256"
                    ],
                )
            )

        if normalized.startswith(
            "INSERT INTO MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
        ):
            self._begin_locked()

            (
                namespace,
                current_sequence_id,
                current_commitment_sha256,
            ) = params

            rows = self._rows()

            if namespace in rows:
                return ControlledCursor(
                    rowcount=0
                )

            rows[namespace] = {
                "current_sequence_id": (
                    current_sequence_id
                ),
                "current_commitment_sha256": (
                    current_commitment_sha256
                ),
                "pending_transaction_id": None,
                "pending_expected_sequence_id": None,
                "pending_expected_commitment_sha256": None,
                "pending_intended_sequence_id": None,
                "pending_intended_commitment_sha256": None,
            }

            return ControlledCursor(
                rowcount=1
            )

        if (
            normalized.startswith(
                "UPDATE MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
            )
            and
            "PENDING_TRANSACTION_ID = %S"
            in normalized
        ):
            self._begin_locked()

            (
                transaction_id,
                expected_sequence_id,
                expected_commitment,
                intended_sequence_id,
                intended_commitment,
                namespace,
            ) = params

            row = self._rows()[
                namespace
            ]

            row[
                "pending_transaction_id"
            ] = transaction_id

            row[
                "pending_expected_sequence_id"
            ] = expected_sequence_id

            row[
                "pending_expected_commitment_sha256"
            ] = expected_commitment

            row[
                "pending_intended_sequence_id"
            ] = intended_sequence_id

            row[
                "pending_intended_commitment_sha256"
            ] = intended_commitment

            return ControlledCursor(
                rowcount=1
            )

        if (
            normalized.startswith(
                "UPDATE MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
            )
            and
            "CURRENT_SEQUENCE_ID = %S"
            in normalized
            and
            "PENDING_TRANSACTION_ID = NULL"
            in normalized
        ):
            self._begin_locked()

            (
                current_sequence_id,
                current_commitment,
                namespace,
            ) = params

            row = self._rows()[
                namespace
            ]

            row[
                "current_sequence_id"
            ] = current_sequence_id

            row[
                "current_commitment_sha256"
            ] = current_commitment

            row[
                "pending_transaction_id"
            ] = None

            row[
                "pending_expected_sequence_id"
            ] = None

            row[
                "pending_expected_commitment_sha256"
            ] = None

            row[
                "pending_intended_sequence_id"
            ] = None

            row[
                "pending_intended_commitment_sha256"
            ] = None

            return ControlledCursor(
                rowcount=1
            )

        if (
            normalized.startswith(
                "UPDATE MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
            )
            and
            "SET PENDING_TRANSACTION_ID = NULL"
            in normalized
        ):
            self._begin_locked()

            namespace = params[0]

            row = self._rows()[
                namespace
            ]

            row[
                "pending_transaction_id"
            ] = None

            row[
                "pending_expected_sequence_id"
            ] = None

            row[
                "pending_expected_commitment_sha256"
            ] = None

            row[
                "pending_intended_sequence_id"
            ] = None

            row[
                "pending_intended_commitment_sha256"
            ] = None

            return ControlledCursor(
                rowcount=1
            )

        raise AssertionError(
            "UNEXPECTED_SQL:"
            + normalized
        )

    def commit(
        self,
    ):
        if self._locked:
            self.store.rows = (
                copy.deepcopy(
                    self._working_rows
                )
            )

            self.store.commit_count += 1

            self.store.lock.release()

            self._locked = False
            self._working_rows = None

    def rollback(
        self,
    ):
        if self._locked:
            self.store.rollback_count += 1

            self.store.lock.release()

            self._locked = False
            self._working_rows = None

    def close(
        self,
    ):
        if self._locked:
            self.rollback()

        if not self._closed:
            self.store.close_count += 1
            self._closed = True


def make_root(
    store,
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        TEST_DSN,
    )

    return PostgresFreshnessRoot(
        dsn_secret_ref=(
            EnvironmentSecretRef(
                variable_name=SECRET_ENV,
                min_length=16,
            )
        ),
        connect_factory=store.connect,
    )


def test_read_missing_namespace_returns_none(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.read(
        NAMESPACE
    ) is None

    assert store.close_count == 1


def test_initialize_is_atomic_and_idempotent(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.read(
        NAMESPACE
    ) == GENESIS

    # Exact repeated initialization is idempotent.
    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    # Different initialization never rebases authority.
    assert not root.initialize(
        namespace=NAMESPACE,
        state=STATE_A,
    )

    assert root.read(
        NAMESPACE
    ) == GENESIS


def test_prepare_persists_exact_pending_reservation(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    pending = root.read_pending(
        NAMESPACE
    )

    assert pending is not None
    assert pending.namespace == NAMESPACE
    assert pending.transaction_id == "tx-a"
    assert pending.expected == GENESIS
    assert pending.intended == STATE_A

    assert root.read(
        NAMESPACE
    ) == GENESIS


def test_prepare_has_single_winner_and_same_reservation_is_idempotent(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    assert not root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_B,
        transaction_id="tx-b",
    )

    pending = root.read_pending(
        NAMESPACE
    )

    assert pending.transaction_id == "tx-a"
    assert pending.intended == STATE_A


def test_finalize_advances_only_matching_reservation_and_is_idempotent(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    assert not root.finalize(
        namespace=NAMESPACE,
        transaction_id="wrong-tx",
        intended=STATE_A,
    )

    assert root.read(
        NAMESPACE
    ) == GENESIS

    assert root.finalize(
        namespace=NAMESPACE,
        transaction_id="tx-a",
        intended=STATE_A,
    )

    assert root.read(
        NAMESPACE
    ) == STATE_A

    assert root.read_pending(
        NAMESPACE
    ) is None

    # Already-finalized exact transition is idempotent.
    assert root.finalize(
        namespace=NAMESPACE,
        transaction_id="tx-a",
        intended=STATE_A,
    )


def test_abort_clears_only_matching_pending_without_advancing_current(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    assert not root.abort(
        namespace=NAMESPACE,
        transaction_id="wrong-tx",
        expected=GENESIS,
    )

    assert root.abort(
        namespace=NAMESPACE,
        transaction_id="tx-a",
        expected=GENESIS,
    )

    assert root.read(
        NAMESPACE
    ) == GENESIS

    assert root.read_pending(
        NAMESPACE
    ) is None

    # Exact repeated abort is safe/idempotent.
    assert root.abort(
        namespace=NAMESPACE,
        transaction_id="tx-a",
        expected=GENESIS,
    )


def test_compare_and_set_requires_exact_current_and_no_pending(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.compare_and_set(
        namespace=NAMESPACE,
        expected=GENESIS,
        new=STATE_A,
    )

    assert root.read(
        NAMESPACE
    ) == STATE_A

    assert not root.compare_and_set(
        namespace=NAMESPACE,
        expected=GENESIS,
        new=STATE_B,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=STATE_A,
        intended=STATE_C,
        transaction_id="tx-c",
    )

    assert not root.compare_and_set(
        namespace=NAMESPACE,
        expected=STATE_A,
        new=STATE_C,
    )


def test_mutating_sql_uses_row_level_for_update_lock(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    assert root.prepare(
        namespace=NAMESPACE,
        expected=GENESIS,
        intended=STATE_A,
        transaction_id="tx-a",
    )

    normalized_sql = "\n".join(
        sql
        for sql, _
        in store.sql_log
    )

    assert "FOR UPDATE" in normalized_sql


def test_driver_error_rolls_back_and_preserves_authority_state(
    monkeypatch,
):
    store = ControlledPostgresStore()
    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    before = copy.deepcopy(
        store.rows
    )

    store.fail_fragment = (
        "UPDATE MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
    )

    with pytest.raises(
        ValueError,
        match=(
            "POSTGRES_FRESHNESS_ROOT_OPERATION_FAILED"
        ),
    ):
        root.prepare(
            namespace=NAMESPACE,
            expected=GENESIS,
            intended=STATE_A,
            transaction_id="tx-a",
        )

    assert store.rows == before
    assert store.rollback_count >= 1


def test_two_concurrent_connections_from_same_expected_have_one_prepare_winner(
    monkeypatch,
):
    store = ControlledPostgresStore()

    root_a = make_root(
        store,
        monkeypatch,
    )

    root_b = make_root(
        store,
        monkeypatch,
    )

    assert root_a.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    barrier = Barrier(2)

    results = {}
    result_lock = RLock()

    def worker(
        label,
        root,
        intended,
        txid,
    ):
        barrier.wait(
            timeout=10
        )

        try:
            result = root.prepare(
                namespace=NAMESPACE,
                expected=GENESIS,
                intended=intended,
                transaction_id=txid,
            )
        except Exception as error:
            result = error

        with result_lock:
            results[label] = result

    first = Thread(
        target=worker,
        args=(
            "A",
            root_a,
            STATE_A,
            "tx-a",
        ),
        daemon=True,
    )

    second = Thread(
        target=worker,
        args=(
            "B",
            root_b,
            STATE_B,
            "tx-b",
        ),
        daemon=True,
    )

    first.start()
    second.start()

    first.join(
        timeout=15
    )
    second.join(
        timeout=15
    )

    assert not first.is_alive()
    assert not second.is_alive()

    assert set(results) == {
        "A",
        "B",
    }

    assert sorted(
        value
        for value in results.values()
        if isinstance(value, bool)
    ) == [
        False,
        True,
    ]

    pending = root_a.read_pending(
        NAMESPACE
    )

    assert pending is not None

    assert pending.transaction_id in {
        "tx-a",
        "tx-b",
    }

    assert pending.intended in {
        STATE_A,
        STATE_B,
    }
