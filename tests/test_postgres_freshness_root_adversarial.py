from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


# Reuse the already-audited controlled transactional driver
# without duplicating hundreds of lines of test infrastructure.

driver_path = Path(__file__).with_name(
    "test_postgres_freshness_root_sql.py"
)

spec = importlib.util.spec_from_file_location(
    "_matrix_b2id_controlled_driver",
    driver_path,
)

assert spec is not None
assert spec.loader is not None

driver = importlib.util.module_from_spec(
    spec
)

sys.modules[
    spec.name
] = driver

spec.loader.exec_module(
    driver
)


ControlledPostgresStore = (
    driver.ControlledPostgresStore
)

GENESIS = driver.GENESIS
STATE_A = driver.STATE_A
STATE_B = driver.STATE_B
NAMESPACE = driver.NAMESPACE

make_root = driver.make_root


CORRUPT_ROW = (
    "POSTGRES_FRESHNESS_ROOT_CORRUPT_ROW"
)

COMMIT_UNKNOWN = (
    "POSTGRES_FRESHNESS_ROOT_COMMIT_OUTCOME_UNKNOWN"
)


def authority_row(
    store,
):
    return store.rows[
        NAMESPACE
    ]


def inject_orphan_pending_payload(
    store,
):
    row = authority_row(
        store
    )

    assert (
        row[
            "pending_transaction_id"
        ]
        is None
    )

    row[
        "pending_expected_sequence_id"
    ] = GENESIS.sequence_id

    row[
        "pending_expected_commitment_sha256"
    ] = GENESIS.commitment_sha256

    row[
        "pending_intended_sequence_id"
    ] = STATE_A.sequence_id

    row[
        "pending_intended_commitment_sha256"
    ] = STATE_A.commitment_sha256


def inject_current_pending_divergence(
    store,
):
    row = authority_row(
        store
    )

    row[
        "current_sequence_id"
    ] = STATE_A.sequence_id

    row[
        "current_commitment_sha256"
    ] = STATE_A.commitment_sha256

    row[
        "pending_transaction_id"
    ] = "tx-corrupt"

    row[
        "pending_expected_sequence_id"
    ] = GENESIS.sequence_id

    row[
        "pending_expected_commitment_sha256"
    ] = GENESIS.commitment_sha256

    row[
        "pending_intended_sequence_id"
    ] = STATE_B.sequence_id

    row[
        "pending_intended_commitment_sha256"
    ] = STATE_B.commitment_sha256


class CommitAfterDurableRaisesConnection:
    """
    Simulates the dangerous database-client case:

      server-side transaction became durable,
      but the client did not receive a reliable COMMIT result.

    A generic OPERATION_FAILED response is insufficient because
    callers must know that authority state may have advanced.
    """

    def __init__(
        self,
        delegate,
    ):
        self._delegate = delegate

    def execute(
        self,
        sql,
        params=None,
    ):
        return self._delegate.execute(
            sql,
            params,
        )

    def commit(
        self,
    ):
        self._delegate.commit()

        raise ConnectionError(
            "simulated acknowledgement loss after durable commit"
        )

    def rollback(
        self,
    ):
        return self._delegate.rollback()

    def close(
        self,
    ):
        return self._delegate.close()


class AmbiguousCommitStore(
    ControlledPostgresStore
):
    def __init__(
        self,
    ):
        super().__init__()

        self.fail_after_durable_commit = False

    def connect(
        self,
        dsn,
    ):
        connection = super().connect(
            dsn
        )

        if not self.fail_after_durable_commit:
            return connection

        return CommitAfterDurableRaisesConnection(
            connection
        )


def test_orphan_pending_payload_is_corruption_not_empty_pending(
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

    inject_orphan_pending_payload(
        store
    )

    before = copy.deepcopy(
        store.rows
    )

    with pytest.raises(
        ValueError,
        match=CORRUPT_ROW,
    ):
        root.read_pending(
            NAMESPACE
        )

    assert store.rows == before


def test_orphan_pending_payload_cannot_be_silently_cleared_by_cas(
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

    inject_orphan_pending_payload(
        store
    )

    before = copy.deepcopy(
        store.rows
    )

    with pytest.raises(
        ValueError,
        match=CORRUPT_ROW,
    ):
        root.compare_and_set(
            namespace=NAMESPACE,
            expected=GENESIS,
            new=STATE_A,
        )

    assert store.rows == before


def test_pending_expected_must_match_current_before_idempotent_prepare(
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

    inject_current_pending_divergence(
        store
    )

    before = copy.deepcopy(
        store.rows
    )

    with pytest.raises(
        ValueError,
        match=CORRUPT_ROW,
    ):
        root.prepare(
            namespace=NAMESPACE,
            expected=GENESIS,
            intended=STATE_B,
            transaction_id="tx-corrupt",
        )

    assert store.rows == before


def test_ambiguous_initialize_commit_has_distinct_fail_closed_error(
    monkeypatch,
):
    store = AmbiguousCommitStore()

    root = make_root(
        store,
        monkeypatch,
    )

    store.fail_after_durable_commit = True

    with pytest.raises(
        ValueError,
        match=COMMIT_UNKNOWN,
    ):
        root.initialize(
            namespace=NAMESPACE,
            state=GENESIS,
        )

    # The simulated COMMIT was durable even though the
    # acknowledgement was lost.
    store.fail_after_durable_commit = False

    assert root.read(
        NAMESPACE
    ) == GENESIS


def test_ambiguous_prepare_commit_preserves_pending_and_reports_unknown(
    monkeypatch,
):
    store = AmbiguousCommitStore()

    root = make_root(
        store,
        monkeypatch,
    )

    assert root.initialize(
        namespace=NAMESPACE,
        state=GENESIS,
    )

    store.fail_after_durable_commit = True

    with pytest.raises(
        ValueError,
        match=COMMIT_UNKNOWN,
    ):
        root.prepare(
            namespace=NAMESPACE,
            expected=GENESIS,
            intended=STATE_A,
            transaction_id="tx-ambiguous-prepare",
        )

    store.fail_after_durable_commit = False

    pending = root.read_pending(
        NAMESPACE
    )

    assert pending is not None

    assert pending.transaction_id == (
        "tx-ambiguous-prepare"
    )

    assert pending.expected == GENESIS
    assert pending.intended == STATE_A

    assert root.read(
        NAMESPACE
    ) == GENESIS


def test_ambiguous_finalize_commit_reports_unknown_and_recovery_state_is_visible(
    monkeypatch,
):
    store = AmbiguousCommitStore()

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
        transaction_id="tx-ambiguous-finalize",
    )

    store.fail_after_durable_commit = True

    with pytest.raises(
        ValueError,
        match=COMMIT_UNKNOWN,
    ):
        root.finalize(
            namespace=NAMESPACE,
            transaction_id="tx-ambiguous-finalize",
            intended=STATE_A,
        )

    store.fail_after_durable_commit = False

    assert root.read(
        NAMESPACE
    ) == STATE_A

    assert root.read_pending(
        NAMESPACE
    ) is None
