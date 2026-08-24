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


def _canonical_payload(value):
    import hashlib

    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rewrite_r8_2_anchor(path):
    with sqlite3.connect(path) as connection:
        run_rows = connection.execute(
            """
            SELECT
                run_id,
                manifest_fingerprint,
                config_fingerprint,
                provider_key,
                subject_key,
                modalities_json,
                max_capture_rounds,
                max_total_provider_calls,
                max_runtime_ms,
                state,
                state_version,
                created_at,
                updated_at
            FROM football_bounded_run_control
            ORDER BY run_id
            """
        ).fetchall()
        stream_rows = connection.execute(
            """
            SELECT stream_key, last_reserved_sequence
            FROM football_bounded_stream_sequence
            ORDER BY stream_key
            """
        ).fetchall()
        reservation_rows = connection.execute(
            """
            SELECT
                run_id,
                round_index,
                modality,
                stream_key,
                sequence_number,
                state,
                created_at,
                updated_at
            FROM football_bounded_sequence_reservation
            ORDER BY stream_key, sequence_number
            """
        ).fetchall()
        payload = {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [list(row) for row in run_rows],
            "streams": [list(row) for row in stream_rows],
            "reservations": [list(row) for row in reservation_rows],
        }
        connection.execute(
            """
            UPDATE football_bounded_control_anchor
            SET payload_sha256 = ?
            WHERE singleton_id = 1
            """,
            (_canonical_payload(payload),),
        )
        connection.commit()


def _active_store(tmp_path, name="control.sqlite3"):
    path = tmp_path / name
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    return path, store, value, guard, lease


def test_run_state_time_cannot_regress(tmp_path):
    path = tmp_path / "run-time.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    with pytest.raises(ValueError, match="R8_2_RUN_TIME_REGRESSION"):
        store.transition_run_state(
            value.run_id,
            expected_state="PLANNED",
            expected_state_version=0,
            new_state="IN_PROGRESS",
            changed_at=BASE - timedelta(seconds=1),
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_sequence_reservation_and_transition_time_cannot_regress(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "reservation-time.sqlite3",
    )

    with pytest.raises(
        ValueError,
        match="R8_2_RESERVATION_TIME_PRECEDES_RUN_STATE",
    ):
        store.reserve_next_sequence(
            value.run_id,
            round_index=1,
            modality="fixture_events",
            reserved_at=BASE,
            guard=guard,
            lease=lease,
        )

    reserved = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    assert reserved.state == "RESERVED"

    with pytest.raises(
        ValueError,
        match="R8_2_RESERVATION_TIME_REGRESSION",
    ):
        store.transition_reservation(
            value.run_id,
            round_index=1,
            modality="fixture_events",
            expected_state="RESERVED",
            new_state="COMMITTED",
            changed_at=BASE + timedelta(seconds=1),
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_integrity_rederives_run_config_contract_after_rehashed_tamper(tmp_path):
    path = tmp_path / "run-contract.sqlite3"
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
            SET subject_key = 'team:1',
                modalities_json = '["odds"]',
                max_capture_rounds = 10001,
                max_total_provider_calls = 30001,
                max_runtime_ms = 86400001
            WHERE run_id = ?
            """,
            (value.run_id,),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_integrity_rederives_reservation_stream_key_after_rehashed_tamper(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "stream-key.sqlite3",
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    forged_stream = "f" * 64
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET stream_key = ?
            WHERE run_id = ?
            """,
            (forged_stream, value.run_id),
        )
        connection.execute(
            "DELETE FROM football_bounded_stream_sequence"
        )
        connection.execute(
            """
            INSERT INTO football_bounded_stream_sequence (
                stream_key,
                last_reserved_sequence
            )
            VALUES (?, 1)
            """,
            (forged_stream,),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_integrity_rederives_reservation_slot_contract_after_rehashed_tamper(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "slot-contract.sqlite3",
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    forged_stream = SQLiteBoundedFootballLiveControlStore._stream_key(
        subject_key="fixture:1557375",
        provider_key="api_football",
        modality="odds",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET round_index = 99,
                modality = 'odds',
                stream_key = ?
            WHERE run_id = ?
            """,
            (forged_stream, value.run_id),
        )
        connection.execute(
            "DELETE FROM football_bounded_stream_sequence"
        )
        connection.execute(
            """
            INSERT INTO football_bounded_stream_sequence (
                stream_key,
                last_reserved_sequence
            )
            VALUES (?, 1)
            """,
            (forged_stream,),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_integrity_detects_missing_middle_sequence_after_rehashed_tamper(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "sequence-gap.sqlite3",
    )
    for round_index in (1, 2, 3):
        store.reserve_next_sequence(
            value.run_id,
            round_index=round_index,
            modality="fixture_events",
            reserved_at=BASE + timedelta(seconds=round_index + 1),
            guard=guard,
            lease=lease,
        )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            DELETE FROM football_bounded_sequence_reservation
            WHERE run_id = ?
              AND round_index = 2
              AND modality = 'fixture_events'
            """,
            (value.run_id,),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_integrity_rederives_terminal_open_reservation_invariant(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "terminal.sqlite3",
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET state = 'COMPLETED',
                state_version = state_version + 1,
                updated_at = ?
            WHERE run_id = ?
            """,
            (
                (BASE + timedelta(seconds=3)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_v82_empty_control_store_migrates_atomically_to_v85(tmp_path):
    path = tmp_path / "v82.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 82;
            CREATE TABLE football_bounded_run_control (
                run_id TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                modalities_json TEXT NOT NULL,
                max_capture_rounds INTEGER NOT NULL,
                max_total_provider_calls INTEGER NOT NULL,
                max_runtime_ms INTEGER NOT NULL,
                state TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE football_bounded_stream_sequence (
                stream_key TEXT PRIMARY KEY,
                last_reserved_sequence INTEGER NOT NULL
            );
            CREATE TABLE football_bounded_sequence_reservation (
                run_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                modality TEXT NOT NULL,
                stream_key TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, round_index, modality),
                UNIQUE (stream_key, sequence_number)
            );
            CREATE TABLE football_bounded_control_anchor (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                payload_sha256 TEXT NOT NULL
            );
            """
        )
        empty_payload = {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [],
            "streams": [],
            "reservations": [],
        }
        connection.execute(
            """
            INSERT INTO football_bounded_control_anchor (
                singleton_id,
                payload_sha256
            )
            VALUES (1, ?)
            """,
            (_canonical_payload(empty_payload),),
        )
        connection.commit()

    store = SQLiteBoundedFootballLiveControlStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 86
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(football_bounded_run_control)"
            ).fetchall()
        }

    assert "config_fingerprint" in columns
    assert "manifest_json" in columns
    assert store.audit_integrity() is True


def _anchor_payload_v84(connection):
    run_rows = connection.execute(
        """
        SELECT
            run_id,
            manifest_fingerprint,
            manifest_json,
            config_fingerprint,
            provider_key,
            subject_key,
            modalities_json,
            max_capture_rounds,
            max_total_provider_calls,
            max_runtime_ms,
            state,
            state_version,
            created_at,
            updated_at
        FROM football_bounded_run_control
        ORDER BY run_id
        """
    ).fetchall()
    stream_rows = connection.execute(
        """
        SELECT stream_key, last_reserved_sequence
        FROM football_bounded_stream_sequence
        ORDER BY stream_key
        """
    ).fetchall()
    reservation_rows = connection.execute(
        """
        SELECT
            run_id,
            round_index,
            modality,
            stream_key,
            sequence_number,
            state,
            created_at,
            updated_at
        FROM football_bounded_sequence_reservation
        ORDER BY stream_key, sequence_number
        """
    ).fetchall()
    return {
        "schema": "matrix.c2-r8-2-control-anchor/1",
        "runs": [list(row) for row in run_rows],
        "streams": [list(row) for row in stream_rows],
        "reservations": [list(row) for row in reservation_rows],
    }


def _rewrite_r8_2r2_anchor(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_control_anchor
            SET payload_sha256 = ?
            WHERE singleton_id = 1
            """,
            (_canonical_payload(_anchor_payload_v84(connection)),),
        )
        connection.commit()


def test_manifest_authority_is_rederived_after_rehashed_tamper(tmp_path):
    path = tmp_path / "manifest-authority.sqlite3"
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
            SET manifest_fingerprint = ?
            WHERE run_id = ?
            """,
            ("f" * 64, value.run_id),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_run_id_provenance_is_rederived_from_durable_manifest(tmp_path):
    path = tmp_path / "run-id.sqlite3"
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
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET run_id = ?
            WHERE run_id = ?
            """,
            ("e" * 64, value.run_id),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_stream_sequence_reservation_time_is_monotonic(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "stream-time.sqlite3",
    )

    first = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=10),
        guard=guard,
        lease=lease,
    )
    assert first.sequence_number == 1

    with pytest.raises(
        ValueError,
        match="R8_2_STREAM_SEQUENCE_TIME_REGRESSION",
    ):
        store.reserve_next_sequence(
            value.run_id,
            round_index=2,
            modality="fixture_events",
            reserved_at=BASE + timedelta(seconds=5),
            guard=guard,
            lease=lease,
        )

    guard.release(lease)


def test_integrity_rederives_stream_sequence_time_order(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "stream-time-integrity.sqlite3",
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=2,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET created_at = ?,
                updated_at = ?
            WHERE run_id = ?
              AND round_index = 2
              AND modality = 'fixture_events'
            """,
            (
                (BASE + timedelta(seconds=1)).isoformat(),
                (BASE + timedelta(seconds=1)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


@pytest.mark.parametrize(
    ("state", "state_version"),
    [
        ("PLANNED", 1),
        ("IN_PROGRESS", 0),
        ("IN_PROGRESS", 2),
        ("RECOVERY_REQUIRED", 1),
        ("RECOVERY_REQUIRED", 3),
        ("COMPLETED", 1),
        ("COMPLETED", 3),
        ("ABORTED", 0),
    ],
)
def test_integrity_rederives_run_state_version_semantics(
    tmp_path,
    state,
    state_version,
):
    path = tmp_path / f"state-version-{state}-{state_version}.sqlite3"
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
            SET state = ?,
                state_version = ?
            WHERE run_id = ?
            """,
            (state, state_version, value.run_id),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def _create_empty_v83(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 83;
            CREATE TABLE football_bounded_run_control (
                run_id TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                config_fingerprint TEXT,
                provider_key TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                modalities_json TEXT NOT NULL,
                max_capture_rounds INTEGER NOT NULL,
                max_total_provider_calls INTEGER NOT NULL,
                max_runtime_ms INTEGER NOT NULL,
                state TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE football_bounded_stream_sequence (
                stream_key TEXT PRIMARY KEY,
                last_reserved_sequence INTEGER NOT NULL
            );
            CREATE TABLE football_bounded_sequence_reservation (
                run_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                modality TEXT NOT NULL,
                stream_key TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, round_index, modality),
                UNIQUE (stream_key, sequence_number)
            );
            CREATE TABLE football_bounded_control_anchor (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                payload_sha256 TEXT NOT NULL
            );
            """
        )
        empty_payload = {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [],
            "streams": [],
            "reservations": [],
        }
        connection.execute(
            """
            INSERT INTO football_bounded_control_anchor (
                singleton_id,
                payload_sha256
            )
            VALUES (1, ?)
            """,
            (_canonical_payload(empty_payload),),
        )
        connection.commit()


def test_empty_v83_control_store_migrates_atomically_to_v85(tmp_path):
    path = tmp_path / "v83-empty.sqlite3"
    _create_empty_v83(path)

    store = SQLiteBoundedFootballLiveControlStore(path)

    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(football_bounded_run_control)"
            ).fetchall()
        }

    assert version == 86
    assert "manifest_json" in columns
    assert store.audit_integrity() is True


def test_nonempty_v83_migration_fails_closed_and_is_atomic(tmp_path):
    path = tmp_path / "v83-nonempty.sqlite3"
    _create_empty_v83(path)
    value = manifest()
    modalities_json = json.dumps(
        list(value.modalities),
        separators=(",", ":"),
        ensure_ascii=False,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO football_bounded_run_control (
                run_id,
                manifest_fingerprint,
                config_fingerprint,
                provider_key,
                subject_key,
                modalities_json,
                max_capture_rounds,
                max_total_provider_calls,
                max_runtime_ms,
                state,
                state_version,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                value.run_id,
                value.manifest_fingerprint,
                value.config_fingerprint,
                value.provider_key,
                value.subject_key,
                modalities_json,
                value.max_capture_rounds,
                value.max_total_provider_calls,
                value.max_runtime_ms,
                "PLANNED",
                0,
                BASE.isoformat(),
                BASE.isoformat(),
            ),
        )
        payload = {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [
                list(
                    connection.execute(
                        """
                        SELECT
                            run_id,
                            manifest_fingerprint,
                            config_fingerprint,
                            provider_key,
                            subject_key,
                            modalities_json,
                            max_capture_rounds,
                            max_total_provider_calls,
                            max_runtime_ms,
                            state,
                            state_version,
                            created_at,
                            updated_at
                        FROM football_bounded_run_control
                        """
                    ).fetchone()
                )
            ],
            "streams": [],
            "reservations": [],
        }
        connection.execute(
            """
            UPDATE football_bounded_control_anchor
            SET payload_sha256 = ?
            WHERE singleton_id = 1
            """,
            (_canonical_payload(payload),),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="R8_2R2_NONEMPTY_V83_MANIFEST_PROVENANCE_UNAVAILABLE",
    ):
        SQLiteBoundedFootballLiveControlStore(path)

    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(football_bounded_run_control)"
            ).fetchall()
        }
        count = connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_control"
        ).fetchone()[0]

    assert version == 83
    assert "manifest_json" not in columns
    assert count == 1


def _schema_contract(path):
    with sqlite3.connect(path) as connection:
        table_info = {
            table: tuple(
                (
                    str(row[1]),
                    str(row[2]).upper(),
                    int(row[3]),
                    int(row[5]),
                )
                for row in connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            )
            for table in (
                "football_bounded_run_control",
                "football_bounded_stream_sequence",
                "football_bounded_sequence_reservation",
                "football_bounded_control_anchor",
            )
        }

        indexes = {}
        for table in table_info:
            items = []
            for row in connection.execute(
                f"PRAGMA index_list({table})"
            ).fetchall():
                if int(row[2]) != 1:
                    continue
                columns = tuple(
                    str(item[2])
                    for item in connection.execute(
                        f"PRAGMA index_info({row[1]})"
                    ).fetchall()
                )
                items.append((str(row[3]), columns))
            indexes[table] = tuple(sorted(items))

        foreign_keys = {
            table: tuple(
                sorted(
                    (
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        str(row[5]),
                        str(row[6]),
                        str(row[7]),
                    )
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({table})"
                    ).fetchall()
                )
            )
            for table in table_info
        }
    return table_info, indexes, foreign_keys


def test_manifest_json_requires_exact_canonical_bytes_after_rehashed_tamper(tmp_path):
    path = tmp_path / "manifest-json-bytes.sqlite3"
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
        raw = str(
            connection.execute(
                """
                SELECT manifest_json
                FROM football_bounded_run_control
                WHERE run_id = ?
                """,
                (value.run_id,),
            ).fetchone()[0]
        )
        parsed = json.loads(raw)
        noncanonical = json.dumps(
            parsed,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        assert noncanonical != raw
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET manifest_json = ?
            WHERE run_id = ?
            """,
            (noncanonical, value.run_id),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_empty_v83_migration_produces_exact_fresh_v85_schema_contract(tmp_path):
    fresh_path = tmp_path / "fresh-v85.sqlite3"
    SQLiteBoundedFootballLiveControlStore(fresh_path)

    migrated_path = tmp_path / "migrated-v83.sqlite3"
    _create_empty_v83(migrated_path)
    migrated = SQLiteBoundedFootballLiveControlStore(migrated_path)

    with sqlite3.connect(migrated_path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 86

    assert migrated.audit_integrity() is True
    assert _schema_contract(migrated_path) == _schema_contract(fresh_path)


def test_integrity_rederives_sqlite_schema_constraint_contract(tmp_path):
    path = tmp_path / "schema-drift.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            ALTER TABLE football_bounded_sequence_reservation
            RENAME TO old_reservation
            """
        )
        connection.execute(
            """
            CREATE TABLE football_bounded_sequence_reservation (
                run_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                modality TEXT NOT NULL,
                stream_key TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute("DROP TABLE old_reservation")
        connection.commit()

    assert store.audit_integrity() is False


def test_exact_run_round_modality_slot_uniqueness_is_semantically_rederived(tmp_path):
    path, store, value, guard, lease = _active_store(
        tmp_path,
        "duplicate-slot.sqlite3",
    )
    reserved = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            ALTER TABLE football_bounded_sequence_reservation
            RENAME TO old_reservation
            """
        )
        connection.execute(
            """
            CREATE TABLE football_bounded_sequence_reservation (
                run_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                modality TEXT NOT NULL,
                stream_key TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        rows = connection.execute(
            """
            SELECT
                run_id,
                round_index,
                modality,
                stream_key,
                sequence_number,
                state,
                created_at,
                updated_at
            FROM old_reservation
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                INSERT INTO football_bounded_sequence_reservation
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(row),
            )
        duplicate = list(rows[0])
        duplicate[4] = 2
        duplicate[6] = (BASE + timedelta(seconds=3)).isoformat()
        duplicate[7] = duplicate[6]
        connection.execute(
            """
            INSERT INTO football_bounded_sequence_reservation
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(duplicate),
        )
        connection.execute("DROP TABLE old_reservation")
        connection.execute(
            """
            UPDATE football_bounded_stream_sequence
            SET last_reserved_sequence = 2
            WHERE stream_key = ?
            """,
            (reserved.stream_key,),
        )
        connection.commit()

    _rewrite_r8_2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_nonempty_v84_migrates_to_v85_after_verified_provenance(tmp_path):
    path = tmp_path / "v84-nonempty.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)
    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    guard.release(lease)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE football_bounded_run_transition_event")
        connection.execute("PRAGMA user_version = 84")
        connection.execute(
            """
            UPDATE football_bounded_control_anchor
            SET payload_sha256 = ?
            WHERE singleton_id = 1
            """,
            (_canonical_payload(_anchor_payload_v84(connection)),),
        )
        connection.commit()

    reopened = SQLiteBoundedFootballLiveControlStore(path)
    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

    assert version == 86
    assert reopened.get_run(value.run_id).run_id == value.run_id
    assert reopened.audit_integrity() is True


def test_schema_contract_rejects_unexpected_trigger_namespace(tmp_path):
    path = tmp_path / "trigger-namespace.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER force_abort_after_start
            AFTER UPDATE OF state
            ON football_bounded_run_control
            WHEN NEW.state = 'IN_PROGRESS'
            BEGIN
                UPDATE football_bounded_run_control
                SET state = 'ABORTED'
                WHERE run_id = NEW.run_id;
            END
            """
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_exact_slot_replay_uses_durable_identity_after_recovery(tmp_path):
    path = tmp_path / "recovery-idempotent-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    original = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="RECOVERY_REQUIRED",
        expected_state_version=2,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )

    replay_original_time = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=original.created_at,
        guard=guard,
        lease=lease,
    )
    replay_fresh_time = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=5),
        guard=guard,
        lease=lease,
    )

    assert replay_original_time == original
    assert replay_fresh_time == original
    assert store.get_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
    ) == original

    with sqlite3.connect(path) as connection:
        count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM football_bounded_sequence_reservation
                WHERE run_id = ?
                  AND round_index = 1
                  AND modality = 'fixture_events'
                """,
                (value.run_id,),
            ).fetchone()[0]
        )
        watermark = int(
            connection.execute(
                """
                SELECT last_reserved_sequence
                FROM football_bounded_stream_sequence
                WHERE stream_key = ?
                """,
                (original.stream_key,),
            ).fetchone()[0]
        )

    assert count == 1
    assert watermark == 1
    guard.release(lease)


def test_schema_contract_rejects_semantic_table_sql_drift(tmp_path):
    path = tmp_path / "table-sql-semantics.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            CREATE TABLE replacement_run_control (
                run_id TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                config_fingerprint TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                modalities_json TEXT NOT NULL,
                max_capture_rounds INTEGER NOT NULL,
                max_total_provider_calls INTEGER NOT NULL,
                max_runtime_ms INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state <> 'IN_PROGRESS'),
                state_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "DROP TABLE football_bounded_run_control"
        )
        connection.execute(
            """
            ALTER TABLE replacement_run_control
            RENAME TO football_bounded_run_control
            """
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_committed_result_replay_uses_durable_state_after_recovery(tmp_path):
    path = tmp_path / "committed-result-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    committed = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="RECOVERY_REQUIRED",
        expected_state_version=2,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=5),
        guard=guard,
        lease=lease,
    )

    replay_original = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=committed.updated_at,
        guard=guard,
        lease=lease,
    )
    replay_fresh = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=6),
        guard=guard,
        lease=lease,
    )

    assert replay_original == committed
    assert replay_fresh == committed
    assert store.get_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
    ) == committed
    assert store.audit_integrity() is True
    guard.release(lease)


def test_committed_result_replay_is_read_only_after_run_completion(tmp_path):
    path = tmp_path / "committed-replay-completed-run.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    committed = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )

    replay = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=committed.updated_at,
        guard=guard,
        lease=lease,
    )

    assert replay == committed
    assert store.audit_integrity() is True
    guard.release(lease)


def test_abandoned_result_replay_is_read_only_after_run_abort(tmp_path):
    path = tmp_path / "abandoned-replay-aborted-run.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    reserved = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="ABORTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    abandoned = store.get_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
    )
    assert abandoned.state == "ABANDONED"
    assert abandoned.sequence_number == reserved.sequence_number

    replay = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="ABANDONED",
        changed_at=reserved.created_at,
        guard=guard,
        lease=lease,
    )

    assert replay == abandoned
    assert store.audit_integrity() is True
    guard.release(lease)


def test_run_state_exact_transition_replay_is_idempotent(tmp_path):
    path = tmp_path / "run-state-exact-replay.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    changed = BASE + timedelta(seconds=1)
    first = store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=changed,
        guard=guard,
        lease=lease,
    )
    replay = store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=changed,
        guard=guard,
        lease=lease,
    )

    assert replay == first
    assert replay.state == "IN_PROGRESS"
    assert replay.state_version == 1
    assert replay.updated_at == changed
    assert store.audit_integrity() is True
    guard.release(lease)


def test_run_state_replay_with_different_timestamp_remains_compare_and_swap_failure(
    tmp_path,
):
    path = tmp_path / "run-state-replay-different-time.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )

    with pytest.raises(
        ValueError,
        match="R8_2_RUN_STATE_COMPARE_AND_SWAP_FAILED",
    ):
        store.transition_run_state(
            value.run_id,
            expected_state="PLANNED",
            expected_state_version=0,
            new_state="IN_PROGRESS",
            changed_at=BASE + timedelta(seconds=2),
            guard=guard,
            lease=lease,
        )

    assert store.get_run(value.run_id).state_version == 1
    assert store.audit_integrity() is True
    guard.release(lease)


def test_recovery_state_transition_exact_replay_is_idempotent(tmp_path):
    path = tmp_path / "recovery-state-exact-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    changed = BASE + timedelta(seconds=2)
    first = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=changed,
        guard=guard,
        lease=lease,
    )
    replay = store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=changed,
        guard=guard,
        lease=lease,
    )

    assert replay == first
    assert replay.state == "RECOVERY_REQUIRED"
    assert replay.state_version == 2
    assert store.audit_integrity() is True
    guard.release(lease)


def test_integrity_rejects_noncanonical_run_timestamp_offset_after_anchor_rehash(
    tmp_path,
):
    path = tmp_path / "noncanonical-run-time.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )

    equivalent = (BASE - timedelta(hours=12)).replace(
        tzinfo=__import__("datetime").timezone(-timedelta(hours=12))
    ).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET updated_at = ?
            WHERE run_id = ?
            """,
            (equivalent, value.run_id),
        )
        connection.commit()
    _rewrite_r8_2r2_anchor(path)

    assert store.audit_integrity() is False
    guard.release(lease)


def test_integrity_rejects_noncanonical_reservation_timestamp_offset_after_anchor_rehash(
    tmp_path,
):
    path = tmp_path / "noncanonical-reservation-time.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    committed_at = BASE + timedelta(seconds=12)
    store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=committed_at,
        guard=guard,
        lease=lease,
    )

    equivalent = (committed_at - timedelta(hours=12)).replace(
        tzinfo=__import__("datetime").timezone(-timedelta(hours=12))
    ).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET updated_at = ?
            WHERE run_id = ?
              AND round_index = 1
              AND modality = 'fixture_events'
            """,
            (equivalent, value.run_id),
        )
        connection.commit()
    _rewrite_r8_2r2_anchor(path)

    assert store.audit_integrity() is False
    guard.release(lease)


def test_run_state_replay_rejects_impossible_predecessor_semantics(tmp_path):
    path = tmp_path / "run-state-replay-impossible-predecessor.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = manifest()
    guard, lease = acquire(path)

    store.register_run(
        value,
        guard=guard,
        lease=lease,
        registered_at=BASE,
    )
    changed = BASE + timedelta(seconds=1)
    first = store.transition_run_state(
        value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=changed,
        guard=guard,
        lease=lease,
    )

    with pytest.raises(
        ValueError,
        match="R8_2_RUN_STATE_VERSION_SEMANTICS_INVALID",
    ):
        store.transition_run_state(
            value.run_id,
            expected_state="RECOVERY_REQUIRED",
            expected_state_version=0,
            new_state="IN_PROGRESS",
            changed_at=changed,
            guard=guard,
            lease=lease,
        )

    assert store.get_run(value.run_id) == first
    assert store.audit_integrity() is True
    guard.release(lease)


def test_exact_slot_replay_remains_available_after_completed_run(tmp_path):
    path = tmp_path / "terminal-completed-slot-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    original = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    committed = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )

    replay = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=original.created_at,
        guard=guard,
        lease=lease,
    )

    assert replay.sequence_number == original.sequence_number == 1
    assert replay.stream_key == original.stream_key
    assert replay.created_at == original.created_at
    assert replay.state == committed.state == "COMMITTED"
    assert store.audit_integrity() is True
    guard.release(lease)


def test_exact_slot_replay_remains_available_after_aborted_run(tmp_path):
    path = tmp_path / "terminal-aborted-slot-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    original = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="ABORTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    replay = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=original.created_at,
        guard=guard,
        lease=lease,
    )

    assert replay.sequence_number == original.sequence_number == 1
    assert replay.stream_key == original.stream_key
    assert replay.created_at == original.created_at
    assert replay.state == "ABANDONED"
    assert store.audit_integrity() is True
    guard.release(lease)


def test_terminal_run_cannot_allocate_a_new_slot(tmp_path):
    path = tmp_path / "terminal-new-slot-denied.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    with pytest.raises(
        ValueError,
        match="R8_2_SEQUENCE_RESERVATION_REQUIRES_IN_PROGRESS_RUN",
    ):
        store.reserve_next_sequence(
            value.run_id,
            round_index=1,
            modality="fixture_events",
            reserved_at=BASE + timedelta(seconds=3),
            guard=guard,
            lease=lease,
        )

    assert store.audit_integrity() is True
    guard.release(lease)


def test_exact_slot_replay_remains_available_while_recovery_required(tmp_path):
    path = tmp_path / "recovery-required-slot-replay.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    original = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="RECOVERY_REQUIRED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    replay = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=original.created_at,
        guard=guard,
        lease=lease,
    )

    assert replay == original
    assert store.get_run(value.run_id).state == "RECOVERY_REQUIRED"
    assert store.audit_integrity() is True
    guard.release(lease)


def test_modalities_json_requires_exact_canonical_bytes_after_rehashed_tamper(tmp_path):
    path = tmp_path / "modalities-json-bytes.sqlite3"
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
        raw = str(
            connection.execute(
                """
                SELECT modalities_json
                FROM football_bounded_run_control
                WHERE run_id = ?
                """,
                (value.run_id,),
            ).fetchone()[0]
        )
        parsed = json.loads(raw)
        noncanonical = json.dumps(
            parsed,
            ensure_ascii=False,
            indent=2,
        )
        assert noncanonical != raw
        connection.execute(
            """
            UPDATE football_bounded_run_control
            SET modalities_json = ?
            WHERE run_id = ?
            """,
            (noncanonical, value.run_id),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_process_guard_rejects_hostname_provenance_tamper(tmp_path):
    path = tmp_path / "guard-hostname.sqlite3"
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    lock_path = Path(lease.lock_path)

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["hostname"] = "tampered-host.invalid"
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_LOCK_HOSTNAME_MISMATCH",
    ):
        guard.assert_active(lease)

    payload["hostname"] = lease.hostname
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    guard.release(lease)


def test_process_guard_rejects_acquired_at_provenance_tamper(tmp_path):
    path = tmp_path / "guard-acquired-at.sqlite3"
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    lock_path = Path(lease.lock_path)

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["acquired_at"] = (BASE + timedelta(hours=6)).isoformat()
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_LOCK_ACQUIRED_AT_MISMATCH",
    ):
        guard.assert_active(lease)

    payload["acquired_at"] = lease.acquired_at.isoformat()
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    guard.release(lease)


def test_process_guard_requires_exact_canonical_lock_bytes_and_declared_fields(tmp_path):
    path = tmp_path / "guard-canonical-bytes.sqlite3"
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    lock_path = Path(lease.lock_path)

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_LOCK_CANONICAL_BYTES_MISMATCH",
    ):
        guard.assert_active(lease)

    payload["unexpected"] = "field"
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_LOCK_PROVENANCE_FIELDS_MISMATCH",
    ):
        guard.assert_active(lease)

    payload.pop("unexpected")
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    guard.release(lease)


def test_completed_run_must_dominate_durable_reservation_result_time_after_rehash(tmp_path):
    path = tmp_path / "completed-terminal-time-dominance.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="COMPLETED",
        changed_at=BASE + timedelta(seconds=4),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET updated_at = ?
            WHERE run_id = ?
              AND round_index = 1
              AND modality = 'fixture_events'
            """,
            (
                (BASE + timedelta(seconds=10)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_aborted_run_must_dominate_auto_abandoned_reservation_time_after_rehash(tmp_path):
    path = tmp_path / "aborted-terminal-time-dominance.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    store.transition_run_state(
        value.run_id,
        expected_state="IN_PROGRESS",
        expected_state_version=1,
        new_state="ABORTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET updated_at = ?
            WHERE run_id = ?
              AND round_index = 1
              AND modality = 'fixture_events'
            """,
            (
                (BASE + timedelta(seconds=10)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


@pytest.mark.parametrize(
    "tampered_pid",
    [
        pytest.param(str(os.getpid()), id="digit-string"),
        pytest.param(float(os.getpid()), id="float"),
        pytest.param(True, id="bool"),
    ],
)
def test_process_guard_rejects_pid_type_confusion(tmp_path, tampered_pid):
    path = tmp_path / "guard-pid-type.sqlite3"
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    lock_path = Path(lease.lock_path)
    original_raw = lock_path.read_text(encoding="utf-8")

    payload = json.loads(original_raw)
    payload["pid"] = tampered_pid
    lock_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="PROCESS_SCOPE_GUARD_LOCK_PID_TYPE_MISMATCH",
    ):
        guard.assert_active(lease)

    lock_path.write_text(original_raw, encoding="utf-8")
    guard.release(lease)


def test_planned_run_updated_at_must_equal_created_at_after_rehash(tmp_path):
    path = tmp_path / "planned-run-quiescent-time.sqlite3"
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
            SET updated_at = ?
            WHERE run_id = ?
            """,
            (
                (BASE + timedelta(seconds=10)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_reserved_reservation_updated_at_must_equal_created_at_after_rehash(tmp_path):
    path = tmp_path / "reserved-quiescent-time.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_sequence_reservation
            SET updated_at = ?
            WHERE run_id = ?
              AND round_index = 1
              AND modality = 'fixture_events'
            """,
            (
                (BASE + timedelta(seconds=10)).isoformat(),
                value.run_id,
            ),
        )
        connection.commit()

    _rewrite_r8_2r2_anchor(path)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_healthy_planned_and_reserved_quiescent_timestamps_still_audit(tmp_path):
    planned_path = tmp_path / "healthy-planned-time.sqlite3"
    planned_store = SQLiteBoundedFootballLiveControlStore(planned_path)
    planned_value = manifest()
    planned_guard, planned_lease = acquire(planned_path)

    planned_store.register_run(
        planned_value,
        guard=planned_guard,
        lease=planned_lease,
        registered_at=BASE,
    )
    assert planned_store.audit_integrity() is True
    planned_guard.release(planned_lease)

    reserved_path = tmp_path / "healthy-reserved-time.sqlite3"
    reserved_store = SQLiteBoundedFootballLiveControlStore(reserved_path)
    reserved_value = manifest()
    reserved_guard, reserved_lease = acquire(reserved_path)

    reserved_store.register_run(
        reserved_value,
        guard=reserved_guard,
        lease=reserved_lease,
        registered_at=BASE,
    )
    reserved_store.transition_run_state(
        reserved_value.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=1),
        guard=reserved_guard,
        lease=reserved_lease,
    )
    reserved = reserved_store.reserve_next_sequence(
        reserved_value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=reserved_guard,
        lease=reserved_lease,
    )
    assert reserved.updated_at == reserved.created_at
    assert reserved_store.audit_integrity() is True
    reserved_guard.release(reserved_lease)


def test_nonquiescent_reservation_updated_at_may_advance(tmp_path):
    path = tmp_path / "committed-result-time.sqlite3"
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
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    reserved = store.reserve_next_sequence(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        reserved_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    committed = store.transition_reservation(
        value.run_id,
        round_index=1,
        modality="fixture_events",
        expected_state="RESERVED",
        new_state="COMMITTED",
        changed_at=BASE + timedelta(seconds=3),
        guard=guard,
        lease=lease,
    )

    assert committed.updated_at > reserved.updated_at
    assert store.audit_integrity() is True
    guard.release(lease)
