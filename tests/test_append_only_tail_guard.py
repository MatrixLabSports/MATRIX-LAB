from __future__ import annotations
import sqlite3
from app.core.append_only_tail_guard import SQLiteAppendOnlyTailGuard


def prepared():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    guard = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
    guard.ensure_schema(connection)
    return connection, guard


def test_tail_guard_detects_guard_tail_deletion_via_sequence_high_water():
    connection, guard = prepared()
    guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
    guard.append(connection, record_id="b", record_payload_sha256="b" * 64)
    connection.execute("DELETE FROM test_tail_guard WHERE record_id = ?", ("b",))
    report = guard.audit(connection, records=(("a", "a" * 64),))
    assert report.ok is False
    assert "APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER_MISMATCH" in report.errors


def test_tail_guard_detects_protected_record_tail_deletion():
    connection, guard = prepared()
    guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
    guard.append(connection, record_id="b", record_payload_sha256="b" * 64)
    report = guard.audit(connection, records=(("a", "a" * 64),))
    assert report.ok is False
    assert "TAIL_GUARD_RECORD_COUNT_MISMATCH" in report.errors
    assert "TAIL_GUARD_RECORD_SET_MISMATCH" in report.errors


def test_tail_guard_exact_replay_is_idempotent():
    connection, guard = prepared()
    guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
    guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
    report = guard.audit(connection, records=(("a", "a" * 64),))
    assert report.ok is True
    assert report.commitments == 1
    assert report.sequence_high_water == 1
