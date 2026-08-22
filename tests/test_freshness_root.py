import threading

import pytest

from app.core.freshness_root import (
    FRESHNESS_ROOT_INVALID_COMMITMENT,
    FRESHNESS_ROOT_NOT_AUTHORIZED_FOR_PRODUCTION,
    FRESHNESS_ROOT_REGRESSION_FORBIDDEN,
    FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE,
    FreshnessRoot,
    FreshnessState,
    InMemoryFreshnessRoot,
    require_production_authorized,
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


def test_freshness_state_genesis_has_no_commitment():
    value = state("ledger-a", 0, "a")

    assert value.sequence_id == 0
    assert value.commitment_sha256 is None


def test_freshness_state_non_genesis_requires_sha256():
    with pytest.raises(
        ValueError,
        match=FRESHNESS_ROOT_INVALID_COMMITMENT,
    ):
        FreshnessState(
            namespace="ledger-a",
            sequence_id=1,
            commitment_sha256=None,
        )


def test_in_memory_root_satisfies_protocol():
    root = InMemoryFreshnessRoot()

    assert isinstance(
        root,
        FreshnessRoot,
    )


def test_in_memory_root_initializes_with_compare_and_set():
    root = InMemoryFreshnessRoot()

    genesis = state(
        "ledger-a",
        0,
        "a",
    )

    assert root.read("ledger-a") is None

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=genesis,
    )

    assert root.read("ledger-a") == genesis


def test_in_memory_root_advances_monotonically():
    root = InMemoryFreshnessRoot()

    zero = state(
        "ledger-a",
        0,
        "a",
    )
    one = state(
        "ledger-a",
        1,
        "a",
    )
    two = state(
        "ledger-a",
        2,
        "b",
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=zero,
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=zero,
        new=one,
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=one,
        new=two,
    )

    assert root.read(
        "ledger-a"
    ) == two


def test_in_memory_root_rejects_regression():
    root = InMemoryFreshnessRoot()

    one = state(
        "ledger-a",
        1,
        "a",
    )
    two = state(
        "ledger-a",
        2,
        "b",
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=two,
    )

    with pytest.raises(
        ValueError,
        match=FRESHNESS_ROOT_REGRESSION_FORBIDDEN,
    ):
        root.compare_and_set(
            namespace="ledger-a",
            expected=two,
            new=one,
        )


def test_in_memory_root_rejects_same_sequence_divergence():
    root = InMemoryFreshnessRoot()

    first = state(
        "ledger-a",
        1,
        "a",
    )
    divergent = state(
        "ledger-a",
        1,
        "b",
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=first,
    )

    with pytest.raises(
        ValueError,
        match=FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE,
    ):
        root.compare_and_set(
            namespace="ledger-a",
            expected=first,
            new=divergent,
        )


def test_compare_and_set_rejects_stale_expected_state():
    root = InMemoryFreshnessRoot()

    zero = state(
        "ledger-a",
        0,
        "a",
    )
    one = state(
        "ledger-a",
        1,
        "a",
    )
    two = state(
        "ledger-a",
        2,
        "b",
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=zero,
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=zero,
        new=one,
    )

    assert (
        root.compare_and_set(
            namespace="ledger-a",
            expected=zero,
            new=two,
        )
        is False
    )

    assert root.read(
        "ledger-a"
    ) == one


def test_concurrent_compare_and_set_has_single_winner():
    root = InMemoryFreshnessRoot()

    genesis = state(
        "ledger-a",
        0,
        "a",
    )

    assert root.compare_and_set(
        namespace="ledger-a",
        expected=None,
        new=genesis,
    )

    candidates = (
        state(
            "ledger-a",
            1,
            "a",
        ),
        state(
            "ledger-a",
            1,
            "b",
        ),
    )

    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def worker(candidate):
        barrier.wait()

        try:
            outcome = root.compare_and_set(
                namespace="ledger-a",
                expected=genesis,
                new=candidate,
            )
        except ValueError:
            outcome = False

        with lock:
            outcomes.append(
                outcome
            )

    threads = [
        threading.Thread(
            target=worker,
            args=(candidate,),
        )
        for candidate in candidates
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert sorted(outcomes) == [
        False,
        True,
    ]

    final = root.read(
        "ledger-a"
    )

    assert final in candidates


def test_development_root_is_not_production_authorized():
    root = InMemoryFreshnessRoot()

    assert root.production_authorized is False

    with pytest.raises(
        ValueError,
        match=FRESHNESS_ROOT_NOT_AUTHORIZED_FOR_PRODUCTION,
    ):
        require_production_authorized(
            root
        )
