from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def policy_fingerprint(ledger):
    return ledger.policy_fingerprint(
        quota_policies={
            "P1": {
                "provider_key": "P1",
                "window_seconds": 60,
                "max_request_units": 10,
            }
        },
        circuit_policies={
            "P1": {
                "provider_key": "P1",
                "failure_threshold": 3,
                "cooldown_seconds": 60,
            }
        },
        retry_policies={
            "P1": {
                "provider_key": "P1",
                "max_attempts": 2,
                "base_delay_seconds": 0.5,
                "max_delay_seconds": 2.0,
            }
        },
        worker_limits={
            "max_items": 10,
            "max_requests": 10,
        },
    )


def start(ledger, sport="tennis"):
    return ledger.start_run(
        sport=sport,
        queue_fingerprint="1" * 64,
        policy_fingerprint=policy_fingerprint(ledger),
        started_at=NOW,
    )


def test_run_id_is_deterministic(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    policy = policy_fingerprint(ledger)

    first = ledger.run_id_for(
        sport="tennis",
        queue_fingerprint="1" * 64,
        policy_fingerprint=policy,
        started_at=NOW,
    )
    second = ledger.run_id_for(
        sport="tennis",
        queue_fingerprint="1" * 64,
        policy_fingerprint=policy,
        started_at=NOW,
    )

    assert first == second
    assert len(first) == 64


def test_start_run_creates_hash_chained_start_event(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    run = start(ledger)

    events = ledger.list_events(run.run_id)

    assert run.status == "RUNNING"
    assert len(events) == 1
    assert events[0]["event_type"] == "RUN_STARTED"
    assert events[0]["previous_event_sha256"] is None


def test_events_are_chained_in_sequence(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    run = start(ledger)

    first_hash = ledger.append_event(
        run_id=run.run_id,
        event_type="PROVIDER_ATTEMPT",
        event_payload={"provider_key": "P1", "attempt": 1},
        created_at=NOW + timedelta(seconds=1),
    )

    ledger.append_event(
        run_id=run.run_id,
        event_type="PROVIDER_RESULT",
        event_payload={"provider_key": "P1", "ok": True},
        created_at=NOW + timedelta(seconds=2),
    )

    events = ledger.list_events(run.run_id)

    assert [event["sequence_no"] for event in events] == [1, 2, 3]
    assert events[2]["previous_event_sha256"] == first_hash


def test_terminal_run_rejects_more_events(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    run = start(ledger)

    ledger.finish_run(
        run_id=run.run_id,
        status="COMPLETED",
        result_payload={"processed": 1, "failed": 0},
        finished_at=NOW + timedelta(seconds=3),
    )

    with pytest.raises(
        ValueError,
        match="RUNTIME_AUDIT_RUN_ALREADY_TERMINAL",
    ):
        ledger.append_event(
            run_id=run.run_id,
            event_type="LATE_EVENT",
            event_payload={},
            created_at=NOW + timedelta(seconds=4),
        )


def test_duplicate_run_is_rejected(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    start(ledger)

    with pytest.raises(
        ValueError,
        match="RUNTIME_AUDIT_RUN_ALREADY_EXISTS",
    ):
        start(ledger)


def test_naive_time_is_rejected(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")

    with pytest.raises(ValueError, match="TIMEZONE_UNVERIFIED"):
        ledger.start_run(
            sport="tennis",
            queue_fingerprint="1" * 64,
            policy_fingerprint=policy_fingerprint(ledger),
            started_at=NOW.replace(tzinfo=None),
        )


def test_sports_are_explicitly_separated(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")

    tennis = ledger.start_run(
        sport="tennis",
        queue_fingerprint="1" * 64,
        policy_fingerprint=policy_fingerprint(ledger),
        started_at=NOW,
    )

    football = ledger.start_run(
        sport="football",
        queue_fingerprint="2" * 64,
        policy_fingerprint=policy_fingerprint(ledger),
        started_at=NOW,
    )

    assert tennis.sport == "tennis"
    assert football.sport == "football"
    assert tennis.run_id != football.run_id


def test_integrity_audit_passes_valid_ledger(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")
    run = start(ledger)

    ledger.finish_run(
        run_id=run.run_id,
        status="COMPLETED",
        result_payload={"processed": 1},
        finished_at=NOW + timedelta(seconds=2),
    )

    report = ledger.audit_integrity()

    assert report.ok is True
    assert report.runs == 1
    assert report.events == 2
    assert report.errors == ()


def test_integrity_audit_detects_event_tampering(tmp_path):
    path = tmp_path / "runtime.db"
    ledger = SQLiteRuntimeAuditLedger(path)
    run = start(ledger)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE runtime_audit_events
            SET event_json = ?
            WHERE run_id = ? AND sequence_no = 1
            """,
            ('{"tampered":true}\n', run.run_id),
        )
        connection.commit()

    report = ledger.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("EVENT_HASH_MISMATCH:")
        for error in report.errors
    )


def test_policy_fingerprint_changes_when_policy_changes(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")

    first = ledger.policy_fingerprint(
        quota_policies={"P1": {"limit": 10}},
        circuit_policies={"P1": {"threshold": 3}},
        retry_policies={"P1": {"attempts": 2}},
        worker_limits={"max_requests": 10},
    )

    second = ledger.policy_fingerprint(
        quota_policies={"P1": {"limit": 11}},
        circuit_policies={"P1": {"threshold": 3}},
        retry_policies={"P1": {"attempts": 2}},
        worker_limits={"max_requests": 10},
    )

    assert first != second


def test_policy_fingerprint_is_order_stable(tmp_path):
    ledger = SQLiteRuntimeAuditLedger(tmp_path / "runtime.db")

    first = ledger.policy_fingerprint(
        quota_policies={
            "B": {"x": 2},
            "A": {"x": 1},
        },
        circuit_policies={},
        retry_policies={},
        worker_limits={"max_items": 5, "max_requests": 10},
    )

    second = ledger.policy_fingerprint(
        quota_policies={
            "A": {"x": 1},
            "B": {"x": 2},
        },
        circuit_policies={},
        retry_policies={},
        worker_limits={"max_requests": 10, "max_items": 5},
    )

    assert first == second
