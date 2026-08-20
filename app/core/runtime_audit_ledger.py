from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


_ALLOWED_SPORTS = {"football", "tennis"}
_TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _aware_utc(value).isoformat().replace("+00:00", "Z")


def _validate_sport(sport: object) -> str:
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_SPORT")
    return str(sport)


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    return value.lower()


@dataclass(frozen=True)
class RuntimeAuditRun:
    run_id: str
    sport: str
    queue_fingerprint: str
    policy_fingerprint: str
    started_at: str
    status: str


@dataclass(frozen=True)
class RuntimeAuditIntegrityReport:
    ok: bool
    runs: int
    events: int
    errors: tuple[str, ...]


class SQLiteRuntimeAuditLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_audit_runs (
                    run_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    queue_fingerprint TEXT NOT NULL,
                    policy_fingerprint TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED'))
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_audit_events (
                    run_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL,
                    previous_event_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence_no),
                    FOREIGN KEY (run_id)
                        REFERENCES runtime_audit_runs(run_id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,
                    CHECK (sequence_no >= 1)
                )
                """
            )

    @staticmethod
    def policy_fingerprint(
        *,
        quota_policies: Mapping[str, Mapping[str, Any]],
        circuit_policies: Mapping[str, Mapping[str, Any]],
        retry_policies: Mapping[str, Mapping[str, Any]],
        worker_limits: Mapping[str, Any],
    ) -> str:
        payload = {
            "schema": "matrix.runtime-policy-fingerprint/1",
            "quota_policies": dict(quota_policies),
            "circuit_policies": dict(circuit_policies),
            "retry_policies": dict(retry_policies),
            "worker_limits": dict(worker_limits),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
        return _sha256_text(_canonical_json(payload))

    @staticmethod
    def run_id_for(
        *,
        sport: str,
        queue_fingerprint: str,
        policy_fingerprint: str,
        started_at: datetime,
    ) -> str:
        validated_sport = _validate_sport(sport)
        queue = _validate_hex64("QUEUE_FINGERPRINT", queue_fingerprint)
        policy = _validate_hex64("POLICY_FINGERPRINT", policy_fingerprint)

        payload = {
            "schema": "matrix.runtime-audit-run-id/1",
            "sport": validated_sport,
            "queue_fingerprint": queue,
            "policy_fingerprint": policy,
            "started_at": _iso_utc(started_at),
        }
        return _sha256_text(_canonical_json(payload))

    def start_run(
        self,
        *,
        sport: str,
        queue_fingerprint: str,
        policy_fingerprint: str,
        started_at: datetime,
    ) -> RuntimeAuditRun:
        validated_sport = _validate_sport(sport)
        queue = _validate_hex64("QUEUE_FINGERPRINT", queue_fingerprint)
        policy = _validate_hex64("POLICY_FINGERPRINT", policy_fingerprint)
        started = _iso_utc(started_at)

        run_id = self.run_id_for(
            sport=validated_sport,
            queue_fingerprint=queue,
            policy_fingerprint=policy,
            started_at=started_at,
        )

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO runtime_audit_runs (
                        run_id,
                        sport,
                        queue_fingerprint,
                        policy_fingerprint,
                        started_at,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, 'RUNNING')
                    """,
                    (
                        run_id,
                        validated_sport,
                        queue,
                        policy,
                        started,
                    ),
                )
                connection.execute("COMMIT")
        except sqlite3.IntegrityError as error:
            raise ValueError("RUNTIME_AUDIT_RUN_ALREADY_EXISTS") from error

        self.append_event(
            run_id=run_id,
            event_type="RUN_STARTED",
            event_payload={
                "sport": validated_sport,
                "queue_fingerprint": queue,
                "policy_fingerprint": policy,
                "started_at": started,
            },
            created_at=started_at,
        )

        return RuntimeAuditRun(
            run_id=run_id,
            sport=validated_sport,
            queue_fingerprint=queue,
            policy_fingerprint=policy,
            started_at=started,
            status="RUNNING",
        )

    def append_event(
        self,
        *,
        run_id: str,
        event_type: str,
        event_payload: Mapping[str, Any],
        created_at: datetime,
    ) -> str:
        validated_run = _validate_hex64("RUN_ID", run_id)

        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("INVALID_EVENT_TYPE")

        if not isinstance(event_payload, Mapping):
            raise ValueError("INVALID_EVENT_PAYLOAD")

        created = _iso_utc(created_at)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            run = connection.execute(
                """
                SELECT status
                FROM runtime_audit_runs
                WHERE run_id = ?
                """,
                (validated_run,),
            ).fetchone()

            if run is None:
                connection.execute("ROLLBACK")
                raise ValueError("RUNTIME_AUDIT_RUN_NOT_FOUND")

            if run[0] in _TERMINAL_STATUSES:
                connection.execute("ROLLBACK")
                raise ValueError("RUNTIME_AUDIT_RUN_ALREADY_TERMINAL")

            previous = connection.execute(
                """
                SELECT sequence_no, event_sha256
                FROM runtime_audit_events
                WHERE run_id = ?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (validated_run,),
            ).fetchone()

            sequence_no = 1 if previous is None else int(previous[0]) + 1
            previous_hash = None if previous is None else str(previous[1])

            envelope = {
                "schema": "matrix.runtime-audit-event/1",
                "run_id": validated_run,
                "sequence_no": sequence_no,
                "event_type": event_type,
                "event_payload": dict(event_payload),
                "previous_event_sha256": previous_hash,
                "created_at": created,
            }

            event_json = _canonical_json(envelope)
            event_sha = _sha256_text(event_json)

            connection.execute(
                """
                INSERT INTO runtime_audit_events (
                    run_id,
                    sequence_no,
                    event_type,
                    event_json,
                    event_sha256,
                    previous_event_sha256,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    validated_run,
                    sequence_no,
                    event_type,
                    event_json,
                    event_sha,
                    previous_hash,
                    created,
                ),
            )

            connection.execute("COMMIT")

        return event_sha

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        result_payload: Mapping[str, Any],
        finished_at: datetime,
    ) -> str:
        validated_run = _validate_hex64("RUN_ID", run_id)

        if status not in _TERMINAL_STATUSES:
            raise ValueError("INVALID_TERMINAL_STATUS")

        if not isinstance(result_payload, Mapping):
            raise ValueError("INVALID_RESULT_PAYLOAD")

        finished = _iso_utc(finished_at)

        event_hash = self.append_event(
            run_id=validated_run,
            event_type="RUN_FINISHED",
            event_payload={
                "status": status,
                "result_payload": dict(result_payload),
                "finished_at": finished,
            },
            created_at=finished_at,
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                """
                SELECT status
                FROM runtime_audit_runs
                WHERE run_id = ?
                """,
                (validated_run,),
            ).fetchone()

            if row is None:
                connection.execute("ROLLBACK")
                raise ValueError("RUNTIME_AUDIT_RUN_NOT_FOUND")

            if row[0] != "RUNNING":
                connection.execute("ROLLBACK")
                raise ValueError("RUNTIME_AUDIT_RUN_ALREADY_TERMINAL")

            connection.execute(
                """
                UPDATE runtime_audit_runs
                SET status = ?
                WHERE run_id = ?
                """,
                (status, validated_run),
            )
            connection.execute("COMMIT")

        return event_hash

    def list_events(
        self,
        run_id: str,
    ) -> Sequence[Mapping[str, Any]]:
        validated_run = _validate_hex64("RUN_ID", run_id)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json
                FROM runtime_audit_events
                WHERE run_id = ?
                ORDER BY sequence_no
                """,
                (validated_run,),
            ).fetchall()

        return tuple(json.loads(row[0]) for row in rows)

    def audit_integrity(self) -> RuntimeAuditIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            runs = connection.execute(
                """
                SELECT
                    run_id,
                    sport,
                    queue_fingerprint,
                    policy_fingerprint,
                    started_at,
                    status
                FROM runtime_audit_runs
                ORDER BY run_id
                """
            ).fetchall()

            events = connection.execute(
                """
                SELECT
                    run_id,
                    sequence_no,
                    event_json,
                    event_sha256,
                    previous_event_sha256
                FROM runtime_audit_events
                ORDER BY run_id, sequence_no
                """
            ).fetchall()

        run_ids = {str(row[0]) for row in runs}
        expected_previous: dict[str, str | None] = {}
        expected_sequence: dict[str, int] = {}

        for run_id, sequence_no, event_json, stored_sha, previous_sha in events:
            run_id = str(run_id)
            sequence_no = int(sequence_no)

            if run_id not in run_ids:
                errors.append(f"ORPHAN_EVENT:{run_id}:{sequence_no}")

            try:
                parsed = json.loads(event_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_EVENT_JSON:{run_id}:{sequence_no}")
                continue

            canonical = _canonical_json(parsed)
            actual_sha = _sha256_text(canonical)

            if actual_sha != stored_sha:
                errors.append(f"EVENT_HASH_MISMATCH:{run_id}:{sequence_no}")

            next_sequence = expected_sequence.get(run_id, 1)
            if sequence_no != next_sequence:
                errors.append(f"EVENT_SEQUENCE_GAP:{run_id}:{sequence_no}")

            expected_prev = expected_previous.get(run_id)
            if previous_sha != expected_prev:
                errors.append(f"EVENT_CHAIN_MISMATCH:{run_id}:{sequence_no}")

            if parsed.get("run_id") != run_id:
                errors.append(f"EVENT_RUN_ID_MISMATCH:{run_id}:{sequence_no}")

            if parsed.get("sequence_no") != sequence_no:
                errors.append(f"EVENT_SEQUENCE_MISMATCH:{run_id}:{sequence_no}")

            if parsed.get("previous_event_sha256") != previous_sha:
                errors.append(f"EVENT_PREVIOUS_HASH_MISMATCH:{run_id}:{sequence_no}")

            expected_previous[run_id] = str(stored_sha)
            expected_sequence[run_id] = sequence_no + 1

        for run_id, sport, queue_fp, policy_fp, started_at, status in runs:
            run_id = str(run_id)

            if sport not in _ALLOWED_SPORTS:
                errors.append(f"INVALID_RUN_SPORT:{run_id}")

            try:
                _validate_hex64("QUEUE_FINGERPRINT", queue_fp)
                _validate_hex64("POLICY_FINGERPRINT", policy_fp)
            except ValueError:
                errors.append(f"INVALID_RUN_FINGERPRINT:{run_id}")

            if status not in {"RUNNING", "COMPLETED", "FAILED"}:
                errors.append(f"INVALID_RUN_STATUS:{run_id}")

            run_events = [
                json.loads(row[2])
                for row in events
                if str(row[0]) == run_id
            ]

            if not run_events:
                errors.append(f"RUN_WITHOUT_EVENTS:{run_id}")
                continue

            if run_events[0].get("event_type") != "RUN_STARTED":
                errors.append(f"RUN_MISSING_START_EVENT:{run_id}")

            finish_events = [
                event
                for event in run_events
                if event.get("event_type") == "RUN_FINISHED"
            ]

            if status == "RUNNING" and finish_events:
                errors.append(f"RUNNING_WITH_FINISH_EVENT:{run_id}")

            if status in _TERMINAL_STATUSES and len(finish_events) != 1:
                errors.append(f"TERMINAL_FINISH_COUNT:{run_id}")

        return RuntimeAuditIntegrityReport(
            ok=not errors,
            runs=len(runs),
            events=len(events),
            errors=tuple(errors),
        )
