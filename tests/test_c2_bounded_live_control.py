from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    R8_2_HARD_MAX_CAPTURE_ROUNDS,
    R8_2_HARD_MAX_RUNTIME_MS,
    R8_2_HARD_MAX_TOTAL_PROVIDER_CALLS,
    SQLiteBoundedFootballLiveControlStore,
    iter_bounded_capture_slots_lazy,
    validate_r8_2_engineering_resource_ceiling,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    build_bounded_run_manifest,
)


BASE = datetime(2026, 8, 23, 22, 0, tzinfo=UTC)


def config(**overrides):
    values = dict(
        provider_key="api_football",
        subject_key="fixture:1557375",
        modalities=(
            "fixture_status",
            "fixture_statistics",
            "fixture_events",
        ),
        max_capture_rounds=3,
        max_total_provider_calls=9,
        max_runtime_ms=300000,
    )
    values.update(overrides)
    return BoundedFootballLiveExecutorConfig(**values)


def manifest(**overrides):
    cfg = config(**overrides)
    return build_bounded_run_manifest(
        cfg,
        created_at=BASE,
        run_nonce_sha256="2" * 64,
    )


def acquire(path):
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    return guard, lease


def test_resource_ceiling_accepts_normal_manifest():
    validate_r8_2_engineering_resource_ceiling(manifest())


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {
                "modalities": ("fixture_status",),
                "max_capture_rounds": R8_2_HARD_MAX_CAPTURE_ROUNDS + 1,
                "max_total_provider_calls": R8_2_HARD_MAX_CAPTURE_ROUNDS + 1,
            },
            "R8_2_HARD_CAPTURE_ROUND_CEILING_EXCEEDED",
        ),
        (
            {"max_capture_rounds": 1,
             "max_total_provider_calls": R8_2_HARD_MAX_TOTAL_PROVIDER_CALLS + 1},
            "R8_2_HARD_PROVIDER_CALL_CEILING_EXCEEDED",
        ),
        (
            {"max_capture_rounds": 1,
             "max_total_provider_calls": 3,
             "max_runtime_ms": R8_2_HARD_MAX_RUNTIME_MS + 1},
            "R8_2_HARD_RUNTIME_CEILING_EXCEEDED",
        ),
    ],
)
def test_resource_ceiling_fails_closed(overrides, reason):
    value = manifest(**overrides)
    with pytest.raises(ValueError, match=reason):
        validate_r8_2_engineering_resource_ceiling(value)


def test_lazy_plan_does_not_materialize_full_plan():
    value = config(max_capture_rounds=4, max_total_provider_calls=12)
    iterator = iter_bounded_capture_slots_lazy(value)

    first = next(iterator)
    second = next(iterator)

    assert first.round_index == 1
    assert first.modality == "fixture_status"
    assert second.round_index == 1
    assert second.modality == "fixture_statistics"


def test_process_guard_is_exclusive_and_release_is_owner_checked(tmp_path):
    path = tmp_path / "control.sqlite3"
    first = BoundedExecutorProcessScopeGuard(path)
    lease = first.acquire(acquired_at=BASE)

    second = BoundedExecutorProcessScopeGuard(path)
    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_ALREADY_HELD_OR_STALE",
    ):
        second.acquire(acquired_at=BASE)

    assert first.inspect_lock(path) is not None
    released = first.release(lease)
    assert released.released is True
    assert first.inspect_lock(path) is None


def test_stale_process_guard_fails_closed_without_auto_removal(tmp_path):
    path = tmp_path / "control.sqlite3"
    lock_path = Path(str(path.resolve()) + ".process-scope.lock")
    lock_path.write_text(
        json.dumps({"schema": "stale"}) + "\n",
        encoding="utf-8",
    )

    guard = BoundedExecutorProcessScopeGuard(path)
    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_ALREADY_HELD_OR_STALE",
    ):
        guard.acquire(acquired_at=BASE)

    assert lock_path.exists()


def test_process_guard_exclusion_works_across_python_process(tmp_path):
    path = tmp_path / "control.sqlite3"
    script = r"""
from datetime import UTC, datetime
import sys
from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
)

path = sys.argv[1]
guard = BoundedExecutorProcessScopeGuard(path)
lease = guard.acquire(
    acquired_at=datetime(2026, 8, 23, 22, 0, tzinfo=UTC)
)
print("READY", flush=True)
sys.stdin.readline()
guard.release(lease)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(path)],
        cwd=Path.cwd(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "READY"
        guard = BoundedExecutorProcessScopeGuard(path)
        with pytest.raises(
            ValueError,
            match="PROCESS_SCOPE_GUARD_ALREADY_HELD_OR_STALE",
        ):
            guard.acquire(acquired_at=BASE)
    finally:
        process.stdin.write("\n")
        process.stdin.flush()
        process.wait(timeout=10)
        if process.returncode != 0:
            raise AssertionError(process.stderr.read())


def test_register_run_is_idempotent_and_guard_required(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    first = store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    replay = store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE + timedelta(seconds=1),
    )

    assert first == replay
    assert first.state == "PLANNED"
    assert first.state_version == 0
    assert first.execution_authorized is False
    assert first.production_admissible is False
    assert store.audit_integrity() is True

    guard.release(lease)


def test_manifest_authority_rejects_identity_mutation_before_control_store(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_CONFIG_CONTRACT_FINGERPRINT_MISMATCH",
    ):
        replace(
            value,
            provider_key="provider_b",
            manifest_fingerprint="",
        )

    assert store.get_run(value.run_id).provider_key == "api_football"
    assert store.audit_integrity() is True
    guard.release(lease)


def test_run_recovery_state_machine_is_compare_and_swap_versioned(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    active = store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    assert active.state == "IN_PROGRESS"
    assert active.state_version == 1

    with pytest.raises(
        ValueError,
        match="R8_2_RUN_STATE_VERSION_COMPARE_AND_SWAP_FAILED",
    ):
        store.transition_run_state(
            value.run_id,
            expected_state="IN_PROGRESS",
            expected_state_version=0,
            new_state="RECOVERY_REQUIRED",
            changed_at=BASE + timedelta(seconds=2),
            guard=guard,
            lease=lease,
        )

    recovery = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    assert recovery.state == "RECOVERY_REQUIRED"
    assert recovery.state_version == 2

    resumed = store.transition_run_state(
        value.run_id,
        expected_state="RECOVERY_REQUIRED",
        expected_state_version=2,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    assert resumed.state == "IN_PROGRESS"
    assert resumed.state_version == 3

    completed = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=3,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )
    assert completed.state == "COMPLETED"

    with pytest.raises(
        ValueError,
        match="R8_2_RUN_STATE_TRANSITION_FORBIDDEN",
    ):
        store.transition_run_state(
            value.run_id,
            expected_state="COMPLETED",
            expected_state_version=4,
            new_state="IN_PROGRESS",
            changed_at=BASE + timedelta(seconds=5),
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_sequence_allocator_requires_in_progress_run(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    with pytest.raises(
        ValueError,
        match="R8_2_SEQUENCE_RESERVATION_REQUIRES_IN_PROGRESS_RUN",
    ):
        store.reserve_next_sequence(
            value.run_id,
            round_index=1,
            modality="fixture_status",
            reserved_at=BASE,
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_sequence_allocator_is_stream_scoped_monotonic_and_idempotent(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )

    status_1 = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_status",
        reserved_at=BASE,
        guard=guard,
        lease=lease,
    )
    status_1_replay = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_status",
        reserved_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    status_2 = store.reserve_next_sequence(
        value.run_id,
        round_index=2,
        modality="fixture_status",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    events_1 = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    assert status_1.sequence_number == 1
    assert status_1_replay == status_1
    assert status_2.sequence_number == 2
    assert events_1.sequence_number == 1
    assert status_1.stream_key == status_2.stream_key
    assert events_1.stream_key != status_1.stream_key
    assert store.audit_integrity() is True

    guard.release(lease)


def test_abandoned_sequence_is_never_reused(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )

    first = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE,
        guard=guard,
        lease=lease,
    )
    abandoned = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="ABANDONED",
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    second = store.reserve_next_sequence(
        value.run_id,
        round_index=2,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    assert first.sequence_number == 1
    assert abandoned.state == "ABANDONED"
    assert second.sequence_number == 2

    guard.release(lease)


def test_committed_reservation_transition_is_idempotent(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_statistics",
        reserved_at=BASE,
        guard=guard,
        lease=lease,
    )

    committed = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_statistics",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    replay = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_statistics",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    assert committed.state == "COMMITTED"
    assert replay == committed

    guard.release(lease)


def test_sequence_allocator_rejects_unknown_modality_and_round_overflow(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )

    with pytest.raises(ValueError, match="R8_2_RUN_MODALITY_NOT_ALLOWED"):
        store.reserve_next_sequence(
            value.run_id,
            round_index=1,
            modality="odds",
            reserved_at=BASE,
            guard=guard,
            lease=lease,
        )

    with pytest.raises(
        ValueError,
        match="R8_2_ROUND_INDEX_EXCEEDS_RUN_BOUND",
    ):
        store.reserve_next_sequence(
            value.run_id,
            round_index=4,
            modality="fixture_status",
            reserved_at=BASE,
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_control_store_detects_direct_tampering(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET state = 'COMPLETED'
            WHERE run_id = ?
            """,
            (value.run_id,),
        )
        connection.commit()

    assert store.audit_integrity() is False
    guard.release(lease)


def test_mutations_fail_without_owned_guard(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard = BoundedExecutorProcessScopeGuard(path)
    other_guard = BoundedExecutorProcessScopeGuard(
        tmp_path / "other.sqlite3"
    )
    other_lease = other_guard.acquire(acquired_at=BASE)

    with pytest.raises(
        ValueError,
        match="R8_2_PROCESS_GUARD_PATH_MISMATCH",
    ):
        store.register_run(
            value,
            guard=other_guard,
            lease=other_lease,
            registered_at=BASE,
        )

    other_guard.release(other_lease)


def test_control_plane_never_authorizes_execution_or_production(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    snapshot = store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    assert snapshot.execution_authorized is False
    assert snapshot.production_admissible is False

    guard.release(lease)


def test_completion_fails_with_open_reservation_and_succeeds_after_commit(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE,
        guard=guard,
        lease=lease,
    )

    with pytest.raises(
        ValueError,
        match="R8_2_COMPLETION_WITH_OPEN_RESERVATIONS_FORBIDDEN",
    ):
        store.transition_run_state(
            value.run_id,
            expected_state="IN_PROGRESS",
            expected_state_version=1,
            new_state="COMPLETED",
            changed_at=BASE + timedelta(seconds=1),
            guard=guard,
            lease=lease,
        )

    store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    completed = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    assert completed.state == "COMPLETED"
    guard.release(lease)


def test_abort_atomically_marks_open_reservations_abandoned(tmp_path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE,
        guard=guard,
        lease=lease,
    )
    first = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_status",
        reserved_at=BASE,
        guard=guard,
        lease=lease,
    )
    aborted = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="ABORTED",
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    reservation = store.get_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_status",
    )

    assert aborted.state == "ABORTED"
    assert reservation.sequence_number == first.sequence_number
    assert reservation.state == "ABANDONED"
    assert store.audit_integrity() is True
    guard.release(lease)
