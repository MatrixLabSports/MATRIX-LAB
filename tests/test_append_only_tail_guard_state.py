from __future__ import annotations

import sqlite3

from app.core.append_only_tail_guard import (
    APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN,
    SQLiteAppendOnlyTailGuard,
)


def test_tail_guard_state_blocks_silent_rebaseline_after_guard_table_loss(tmp_path):
    path = tmp_path / "guard.db"
    with sqlite3.connect(path) as connection:
        guard = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
        guard.ensure_schema(connection)
        guard.bootstrap_if_pristine(connection, records=())
        guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
        connection.commit()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE test_tail_guard")
        connection.commit()
    with sqlite3.connect(path) as connection:
        reopened = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
        reopened.ensure_schema(connection)
        reopened.bootstrap_if_pristine(connection, records=(("a", "a" * 64),))
        report = reopened.audit(connection, records=(("a", "a" * 64),))
        assert report.ok is False
        assert APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN in report.errors


def test_tail_guard_state_blocks_append_after_guard_loss(tmp_path):
    path = tmp_path / "guard.db"
    with sqlite3.connect(path) as connection:
        guard = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
        guard.ensure_schema(connection)
        guard.bootstrap_if_pristine(connection, records=())
        guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
        connection.commit()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE test_tail_guard")
        connection.commit()
    with sqlite3.connect(path) as connection:
        reopened = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
        reopened.ensure_schema(connection)
        reopened.bootstrap_if_pristine(connection, records=(("a", "a" * 64),))
        try:
            reopened.append(connection, record_id="b", record_payload_sha256="b" * 64)
        except ValueError as error:
            assert APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN in str(error)
        else:
            raise AssertionError("append must fail closed after guard loss")


def test_tail_guard_state_fresh_database_allows_first_append(tmp_path):
    path = tmp_path / "guard.db"
    with sqlite3.connect(path) as connection:
        guard = SQLiteAppendOnlyTailGuard(table_name="test_tail_guard", ledger_name="test_ledger")
        guard.ensure_schema(connection)
        guard.bootstrap_if_pristine(connection, records=())
        guard.append(connection, record_id="a", record_payload_sha256="a" * 64)
        report = guard.audit(connection, records=(("a", "a" * 64),))
        assert report.ok is True
        assert report.commitments == 1
