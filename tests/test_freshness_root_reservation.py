import inspect

import pytest

from app.core.append_only_tail_guard import (
    SQLiteAppendOnlyTailGuard,
)
from app.core.freshness_root import (
    FreshnessRoot,
    FreshnessState,
    InMemoryFreshnessRoot,
)


def state(namespace, sequence, character):
    commitment = (
        None
        if sequence == 0
        else character * 64
    )

    return FreshnessState(
        namespace=namespace,
        sequence_id=sequence,
        commitment_sha256=commitment,
    )


def test_tail_guard_requires_explicit_scope_when_freshness_root_is_supplied():
    root = InMemoryFreshnessRoot()

    with pytest.raises(
        ValueError,
        match="APPEND_ONLY_TAIL_GUARD_FRESHNESS_SCOPE_REQUIRED",
    ):
        SQLiteAppendOnlyTailGuard(
            table_name="reservation_guard",
            ledger_name="reservation-ledger",
            freshness_root=root,
        )


def test_tail_guard_declares_explicit_freshness_scope_parameter():
    signature = inspect.signature(
        SQLiteAppendOnlyTailGuard.__init__
    )

    assert (
        "freshness_scope_id"
        in signature.parameters
    )


def test_freshness_root_protocol_declares_initialize():
    assert hasattr(
        FreshnessRoot,
        "initialize",
    )


def test_freshness_root_protocol_declares_read_pending():
    assert hasattr(
        FreshnessRoot,
        "read_pending",
    )


def test_freshness_root_protocol_declares_prepare():
    assert hasattr(
        FreshnessRoot,
        "prepare",
    )


def test_freshness_root_protocol_declares_finalize():
    assert hasattr(
        FreshnessRoot,
        "finalize",
    )


def test_freshness_root_protocol_declares_abort():
    assert hasattr(
        FreshnessRoot,
        "abort",
    )


def test_prepare_has_single_winner_for_same_expected_state():
    namespace = (
        "matrix-test/freshness/"
        "reservation-single-winner"
    )

    root = InMemoryFreshnessRoot()

    genesis = state(
        namespace,
        0,
        "a",
    )

    branch_a = state(
        namespace,
        1,
        "a",
    )

    branch_b = state(
        namespace,
        1,
        "b",
    )

    assert root.initialize(
        namespace=namespace,
        state=genesis,
    )

    assert root.prepare(
        namespace=namespace,
        expected=genesis,
        intended=branch_a,
        transaction_id="transaction-a",
    )

    assert (
        root.prepare(
            namespace=namespace,
            expected=genesis,
            intended=branch_b,
            transaction_id="transaction-b",
        )
        is False
    )

    pending = root.read_pending(
        namespace
    )

    assert pending is not None
    assert (
        pending.transaction_id
        == "transaction-a"
    )
    assert pending.expected == genesis
    assert pending.intended == branch_a


def test_finalize_is_idempotent_and_advances_only_reserved_state():
    namespace = (
        "matrix-test/freshness/"
        "reservation-finalize"
    )

    root = InMemoryFreshnessRoot()

    genesis = state(
        namespace,
        0,
        "a",
    )

    intended = state(
        namespace,
        2,
        "b",
    )

    assert root.initialize(
        namespace=namespace,
        state=genesis,
    )

    assert root.prepare(
        namespace=namespace,
        expected=genesis,
        intended=intended,
        transaction_id="transaction-remap",
    )

    assert root.finalize(
        namespace=namespace,
        transaction_id="transaction-remap",
        intended=intended,
    )

    assert root.read(
        namespace
    ) == intended

    assert root.read_pending(
        namespace
    ) is None

    assert root.finalize(
        namespace=namespace,
        transaction_id="transaction-remap",
        intended=intended,
    )

    assert root.read(
        namespace
    ) == intended


def test_abort_clears_uncommitted_reservation_without_advancing_current():
    namespace = (
        "matrix-test/freshness/"
        "reservation-abort"
    )

    root = InMemoryFreshnessRoot()

    genesis = state(
        namespace,
        0,
        "a",
    )

    intended = state(
        namespace,
        1,
        "c",
    )

    assert root.initialize(
        namespace=namespace,
        state=genesis,
    )

    assert root.prepare(
        namespace=namespace,
        expected=genesis,
        intended=intended,
        transaction_id="transaction-abort",
    )

    assert root.abort(
        namespace=namespace,
        transaction_id="transaction-abort",
        expected=genesis,
    )

    assert root.read(
        namespace
    ) == genesis

    assert root.read_pending(
        namespace
    ) is None
