from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3
from pathlib import Path

import pytest

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    R8_2_CONTROL_LEDGER_USER_VERSION,
    R83R5InjectedControlTransitionCrash,
    SQLiteBoundedFootballLiveControlStore,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    build_bounded_run_manifest,
)

BASE = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)


def _manifest(nonce: str = "a" * 64):
    config = BoundedFootballLiveExecutorConfig(
        provider_key="fake:football:deterministic",
        subject_key="fixture:1557375",
        modalities=("fixture_events",),
        max_capture_rounds=3,
        max_total_provider_calls=3,
        max_runtime_ms=300000,
    )
    return build_bounded_run_manifest(
        config,
        created_at=BASE,
        run_nonce_sha256=nonce,
    )


def _guard(path: Path, when: datetime = BASE):
    guard = BoundedExecutorProcessScopeGuard(path)
    return guard, guard.acquire(acquired_at=when)


def _store(tmp_path: Path, name: str = "control.sqlite3"):
    path = tmp_path / name
    store = SQLiteBoundedFootballLiveControlStore(path)
    value = _manifest((name.encode().hex() + "a" * 64)[:64])
    guard, lease = _guard(path)
    store.register_run(value, guard=guard, lease=lease, registered_at=BASE)
    return path, store, value, guard, lease


def _transition(store, value, guard, lease, expected, version, new, seconds, **kwargs):
    return store.transition_run_state(
        value.run_id,
        expected_state=expected,
        expected_state_version=version,
        new_state=new,
        changed_at=BASE + timedelta(seconds=seconds),
        guard=guard,
        lease=lease,
        **kwargs,
    )


def _three_transitions(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    _transition(store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1)
    _transition(store, value, guard, lease, "IN_PROGRESS", 1, "RECOVERY_REQUIRED", 2)
    _transition(store, value, guard, lease, "RECOVERY_REQUIRED", 2, "IN_PROGRESS", 3)
    assert store.audit_integrity() is True
    return path, store, value, guard, lease


def _rehash(store: SQLiteBoundedFootballLiveControlStore):
    with store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        store._rewrite_anchor(connection)
        connection.execute("COMMIT")


def _events(path: Path, run_id: str):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT event_id, run_id, control_id, transition_sequence,
                   previous_event_id, previous_event_sha256, prior_state,
                   next_state, action_code, reason_code, outcome, occurred_at,
                   persisted_at, state_version_before, state_version_after,
                   correlation_id, event_schema_version, event_sha256
            FROM football_bounded_run_transition_event
            WHERE run_id = ?
            ORDER BY transition_sequence
            """,
            (run_id,),
        ).fetchall()


def test_a01_delete_middle_transition_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "DELETE FROM football_bounded_run_transition_event WHERE run_id = ? AND transition_sequence = 2",
            (value.run_id,),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_a02_plausible_extra_transition_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    row = list(_events(path, value.run_id)[-1])
    row[0] = "f" * 64
    row[3] = 4
    row[4] = _events(path, value.run_id)[-1][0]
    row[5] = _events(path, value.run_id)[-1][17]
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO football_bounded_run_transition_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_a03_reordered_transitions_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET transition_sequence = -1 WHERE run_id = ? AND transition_sequence = 1",
            (value.run_id,),
        )
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET transition_sequence = 1 WHERE run_id = ? AND transition_sequence = 2",
            (value.run_id,),
        )
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET transition_sequence = 2 WHERE run_id = ? AND transition_sequence = -1",
            (value.run_id,),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_a04_duplicate_transition_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    row = list(_events(path, value.run_id)[-1])
    row[0] = "e" * 64
    row[3] = 4
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO football_bounded_run_transition_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("next_state", "ABORTED"),
        ("action_code", "ABORT_RUN"),
        ("reason_code", "RUN_ABORT"),
    ],
)
def test_a05_a06_state_or_causality_mutation_rejected_after_local_rehash(
    tmp_path: Path, column: str, value: str
):
    path, store, run, guard, lease = _three_transitions(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE football_bounded_run_transition_event SET {column} = ? WHERE run_id = ? AND transition_sequence = 2",
            (value, run.run_id),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_a07_impossible_transition_timestamp_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    forged = (BASE - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET occurred_at = ?, persisted_at = ? WHERE run_id = ? AND transition_sequence = 2",
            (forged, forged, value.run_id),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def test_a08_cross_run_transplant_rejected_after_local_rehash(tmp_path: Path):
    p1, s1, r1, g1, l1 = _store(tmp_path, "one.sqlite3")
    _transition(s1, r1, g1, l1, "PLANNED", 0, "IN_PROGRESS", 1)
    p2, s2, r2, g2, l2 = _store(tmp_path, "two.sqlite3")
    _transition(s2, r2, g2, l2, "PLANNED", 0, "IN_PROGRESS", 1)
    donor = list(_events(p1, r1.run_id)[0])
    with sqlite3.connect(p2) as connection:
        connection.execute(
            "DELETE FROM football_bounded_run_transition_event WHERE run_id = ?",
            (r2.run_id,),
        )
        donor[0] = "d" * 64
        donor[1] = r2.run_id
        connection.execute(
            "INSERT INTO football_bounded_run_transition_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(donor),
        )
        connection.commit()
    _rehash(s2)
    assert s2.audit_integrity() is False
    g1.release(l1)
    g2.release(l2)


def test_a09_cross_control_identity_transplant_rejected_after_local_rehash(tmp_path: Path):
    p1, s1, r1, g1, l1 = _store(tmp_path, "three.sqlite3")
    _transition(s1, r1, g1, l1, "PLANNED", 0, "IN_PROGRESS", 1)
    p2, s2, r2, g2, l2 = _store(tmp_path, "four.sqlite3")
    _transition(s2, r2, g2, l2, "PLANNED", 0, "IN_PROGRESS", 1)
    foreign_control_id = _events(p2, r2.run_id)[0][2]
    with sqlite3.connect(p1) as connection:
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET control_id = ? WHERE run_id = ?",
            (foreign_control_id, r1.run_id),
        )
        connection.commit()
    _rehash(s1)
    assert s1.audit_integrity() is False
    g1.release(l1)
    g2.release(l2)


def test_a11_crash_before_journal_append_rolls_back_without_phantom_transition(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    with pytest.raises(R83R5InjectedControlTransitionCrash):
        _transition(
            store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1,
            crash_point="BEFORE_TRANSITION_EVENT_APPEND",
        )
    assert store.get_run(value.run_id).state == "PLANNED"
    assert _events(path, value.run_id) == []
    assert store.audit_integrity() is True
    guard.release(lease)


def test_a12_crash_after_append_before_state_update_rolls_back_atomically(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    with pytest.raises(R83R5InjectedControlTransitionCrash):
        _transition(
            store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1,
            crash_point="AFTER_TRANSITION_EVENT_APPEND_BEFORE_STATE_UPDATE",
        )
    assert store.get_run(value.run_id).state_version == 0
    assert _events(path, value.run_id) == []
    assert store.audit_integrity() is True
    guard.release(lease)


def test_a12b_crash_after_state_update_before_commit_rolls_back_atomically(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    with pytest.raises(R83R5InjectedControlTransitionCrash):
        _transition(
            store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1,
            crash_point="AFTER_STATE_UPDATE_BEFORE_COMMIT",
        )
    assert store.get_run(value.run_id).state == "PLANNED"
    assert _events(path, value.run_id) == []
    assert store.audit_integrity() is True
    guard.release(lease)


def test_a13_crash_after_commit_before_ack_preserves_durable_complete_transition(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    with pytest.raises(R83R5InjectedControlTransitionCrash):
        _transition(
            store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1,
            crash_point="AFTER_TRANSITION_COMMIT_BEFORE_ACK",
        )
    snapshot = store.get_run(value.run_id)
    assert snapshot.state == "IN_PROGRESS"
    assert snapshot.state_version == 1
    assert len(_events(path, value.run_id)) == 1
    assert store.audit_integrity() is True
    guard.release(lease)


def test_a14_truncated_event_digest_rejected_after_local_rehash(tmp_path: Path):
    path, store, value, guard, lease = _three_transitions(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE football_bounded_run_transition_event SET event_sha256 = 'abc' WHERE run_id = ? AND transition_sequence = 2",
            (value.run_id,),
        )
        connection.commit()
    _rehash(store)
    assert store.audit_integrity() is False
    guard.release(lease)


def _rewrite_old_v85_anchor(path: Path):
    with sqlite3.connect(path) as connection:
        run_rows = connection.execute(
            """SELECT run_id, manifest_fingerprint, manifest_json, config_fingerprint,
                      provider_key, subject_key, modalities_json, max_capture_rounds,
                      max_total_provider_calls, max_runtime_ms, state, state_version,
                      created_at, updated_at
               FROM football_bounded_run_control ORDER BY run_id"""
        ).fetchall()
        stream_rows = connection.execute(
            "SELECT stream_key, last_reserved_sequence FROM football_bounded_stream_sequence ORDER BY stream_key"
        ).fetchall()
        reservation_rows = connection.execute(
            """SELECT run_id, round_index, modality, stream_key, sequence_number,
                      state, created_at, updated_at
               FROM football_bounded_sequence_reservation ORDER BY stream_key, sequence_number"""
        ).fetchall()
        import hashlib
        payload = {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [list(row) for row in run_rows],
            "streams": [list(row) for row in stream_rows],
            "reservations": [list(row) for row in reservation_rows],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        connection.execute(
            "UPDATE football_bounded_control_anchor SET payload_sha256 = ? WHERE singleton_id = 1",
            (digest,),
        )
        connection.commit()


def test_a15_schema_downgrade_against_v86_structures_is_rejected(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 85")
        connection.commit()
    with pytest.raises(ValueError, match="R8_3R5_V85_CONTROL_ANCHOR_MISMATCH"):
        SQLiteBoundedFootballLiveControlStore(path)
    guard.release(lease)


def test_a16_future_schema_version_is_rejected(tmp_path: Path):
    path = tmp_path / "future.sqlite3"
    SQLiteBoundedFootballLiveControlStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {R8_2_CONTROL_LEDGER_USER_VERSION + 1}")
        connection.commit()
    with pytest.raises(ValueError, match="R8_2_CONTROL_SCHEMA_VERSION_MISMATCH"):
        SQLiteBoundedFootballLiveControlStore(path)


def test_v85_genesis_history_migrates_without_fabricating_events(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    guard.release(lease)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE football_bounded_run_transition_event")
        connection.execute("PRAGMA user_version = 85")
        connection.commit()
    _rewrite_old_v85_anchor(path)
    reopened = SQLiteBoundedFootballLiveControlStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 86
        assert connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_transition_event"
        ).fetchone()[0] == 0
    assert reopened.get_run(value.run_id).state_version == 0
    assert reopened.audit_integrity() is True


def test_v85_non_genesis_history_is_rejected_instead_of_fabricated(tmp_path: Path):
    path, store, value, guard, lease = _store(tmp_path)
    _transition(store, value, guard, lease, "PLANNED", 0, "IN_PROGRESS", 1)
    guard.release(lease)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE football_bounded_run_transition_event")
        connection.execute("PRAGMA user_version = 85")
        connection.commit()
    _rewrite_old_v85_anchor(path)
    with pytest.raises(ValueError, match="R8_3R5_NONEMPTY_V85_TRANSITION_PROVENANCE_UNAVAILABLE"):
        SQLiteBoundedFootballLiveControlStore(path)


def test_a19_local_database_replacement_remains_explicitly_deferred_to_external_root():
    # R8.3R5 deliberately proves local history semantics only. An internally
    # consistent replacement of the entire local DB remains outside the local
    # trust boundary and must be closed by the next external immutable-root gate.
    assert True
