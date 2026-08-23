from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sqlite3
from typing import Any, Iterator, Mapping
from uuid import uuid4

from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    BoundedFootballLiveRunManifest,
    FootballBoundedCaptureSlot,
)


R8_2_PREVIOUS_CONTROL_LEDGER_USER_VERSION = 82
R8_2_CONTROL_LEDGER_USER_VERSION = 83

R8_2_HARD_MAX_CAPTURE_ROUNDS = 10_000
R8_2_HARD_MAX_TOTAL_PROVIDER_CALLS = 30_000
R8_2_HARD_MAX_RUNTIME_MS = 86_400_000

R8_2_RUN_STATES = (
    "PLANNED",
    "IN_PROGRESS",
    "RECOVERY_REQUIRED",
    "COMPLETED",
    "ABORTED",
)

R8_2_RESERVATION_STATES = (
    "RESERVED",
    "COMMITTED",
    "ABANDONED",
)

_R8_2_ALLOWED_TRANSITIONS = {
    "PLANNED": {"IN_PROGRESS", "ABORTED"},
    "IN_PROGRESS": {"RECOVERY_REQUIRED", "COMPLETED", "ABORTED"},
    "RECOVERY_REQUIRED": {"IN_PROGRESS", "ABORTED"},
    "COMPLETED": set(),
    "ABORTED": set(),
}


def _canonical(value: Any) -> str:
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


def _sha(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name.upper()}_MUST_BE_POSITIVE_INTEGER")
    return value


def _nonnegative_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name.upper()}_MUST_BE_NONNEGATIVE_INTEGER")
    return value


def _nonempty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value.strip()


def _sha256_hex(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    normalized = value.strip().lower()
    if (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    return normalized


def validate_r8_2_engineering_resource_ceiling_from_config(
    config: BoundedFootballLiveExecutorConfig,
) -> None:
    if config.max_capture_rounds > R8_2_HARD_MAX_CAPTURE_ROUNDS:
        raise ValueError("R8_2_HARD_CAPTURE_ROUND_CEILING_EXCEEDED")
    if config.max_total_provider_calls > R8_2_HARD_MAX_TOTAL_PROVIDER_CALLS:
        raise ValueError("R8_2_HARD_PROVIDER_CALL_CEILING_EXCEEDED")
    if config.max_runtime_ms > R8_2_HARD_MAX_RUNTIME_MS:
        raise ValueError("R8_2_HARD_RUNTIME_CEILING_EXCEEDED")


def validate_r8_2_engineering_resource_ceiling(
    manifest: BoundedFootballLiveRunManifest,
) -> None:
    rederived = BoundedFootballLiveExecutorConfig(
        provider_key=manifest.provider_key,
        subject_key=manifest.subject_key,
        modalities=manifest.modalities,
        max_capture_rounds=manifest.max_capture_rounds,
        max_total_provider_calls=manifest.max_total_provider_calls,
        max_runtime_ms=manifest.max_runtime_ms,
    )
    validate_r8_2_engineering_resource_ceiling_from_config(rederived)


def iter_bounded_capture_slots_lazy(
    config: BoundedFootballLiveExecutorConfig,
) -> Iterator[FootballBoundedCaptureSlot]:
    if config.max_capture_rounds > R8_2_HARD_MAX_CAPTURE_ROUNDS:
        raise ValueError("R8_2_HARD_CAPTURE_ROUND_CEILING_EXCEEDED")
    if config.max_total_provider_calls > R8_2_HARD_MAX_TOTAL_PROVIDER_CALLS:
        raise ValueError("R8_2_HARD_PROVIDER_CALL_CEILING_EXCEEDED")
    if config.max_runtime_ms > R8_2_HARD_MAX_RUNTIME_MS:
        raise ValueError("R8_2_HARD_RUNTIME_CEILING_EXCEEDED")

    for round_index in range(1, config.max_capture_rounds + 1):
        for modality in config.modalities:
            yield FootballBoundedCaptureSlot(
                round_index=round_index,
                modality=modality,
            )


@dataclass(frozen=True)
class ProcessScopeLease:
    control_path: str
    lock_path: str
    owner_token_sha256: str
    pid: int
    hostname: str
    acquired_at: datetime
    released: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.control_path, name="control_path")
        _nonempty(self.lock_path, name="lock_path")
        _sha256_hex(
            self.owner_token_sha256,
            name="owner_token",
        )
        _positive_int(self.pid, name="pid")
        _nonempty(self.hostname, name="hostname")
        object.__setattr__(
            self,
            "acquired_at",
            _aware_utc(self.acquired_at, name="acquired_at"),
        )


class BoundedExecutorProcessScopeGuard:
    def __init__(self, control_path: str | Path) -> None:
        self.control_path = Path(control_path).resolve()
        self.lock_path = Path(str(self.control_path) + ".process-scope.lock")
        self._owner_token: str | None = None
        self._lease: ProcessScopeLease | None = None

    def acquire(
        self,
        *,
        acquired_at: datetime,
    ) -> ProcessScopeLease:
        if self._lease is not None and not self._lease.released:
            raise ValueError("PROCESS_SCOPE_GUARD_ALREADY_HELD_BY_INSTANCE")

        acquired = _aware_utc(acquired_at, name="acquired_at")
        token = uuid4().hex
        token_sha = sha256(token.encode("utf-8")).hexdigest()
        payload = {
            "schema": "matrix.c2-r8-2-process-scope-guard/1",
            "control_path": str(self.control_path),
            "owner_token_sha256": token_sha,
            "pid": os.getpid(),
            "hostname": platform.node() or "unknown-host",
            "acquired_at": acquired.isoformat(),
        }

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(
                self.lock_path,
                flags,
                0o600,
            )
        except FileExistsError as error:
            raise ValueError(
                "PROCESS_SCOPE_GUARD_ALREADY_HELD_OR_STALE"
            ) from error

        try:
            raw = _canonical(payload).encode("utf-8")
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        lease = ProcessScopeLease(
            control_path=str(self.control_path),
            lock_path=str(self.lock_path),
            owner_token_sha256=token_sha,
            pid=os.getpid(),
            hostname=platform.node() or "unknown-host",
            acquired_at=acquired,
        )
        self._owner_token = token
        self._lease = lease
        return lease

    def _read_lock_payload(self) -> Mapping[str, Any]:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_MISSING") from error
        except json.JSONDecodeError as error:
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_INVALID") from error

        if not isinstance(payload, dict):
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_INVALID")
        return payload

    def assert_active(
        self,
        lease: ProcessScopeLease,
    ) -> None:
        if lease.released:
            raise ValueError("PROCESS_SCOPE_GUARD_LEASE_RELEASED")
        if Path(lease.control_path).resolve() != self.control_path:
            raise ValueError("PROCESS_SCOPE_GUARD_CONTROL_PATH_MISMATCH")
        if Path(lease.lock_path).resolve() != self.lock_path.resolve():
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_PATH_MISMATCH")
        if self._lease != lease or self._owner_token is None:
            raise ValueError("PROCESS_SCOPE_GUARD_LEASE_NOT_OWNED")

        expected_sha = sha256(
            self._owner_token.encode("utf-8")
        ).hexdigest()
        if expected_sha != lease.owner_token_sha256:
            raise ValueError("PROCESS_SCOPE_GUARD_OWNER_TOKEN_MISMATCH")

        payload = self._read_lock_payload()
        if payload.get("schema") != "matrix.c2-r8-2-process-scope-guard/1":
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_SCHEMA_MISMATCH")
        if payload.get("control_path") != str(self.control_path):
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_CONTROL_PATH_MISMATCH")
        if payload.get("owner_token_sha256") != expected_sha:
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_OWNER_MISMATCH")
        if int(payload.get("pid", -1)) != os.getpid():
            raise ValueError("PROCESS_SCOPE_GUARD_PID_MISMATCH")

    def release(
        self,
        lease: ProcessScopeLease,
    ) -> ProcessScopeLease:
        self.assert_active(lease)
        self.lock_path.unlink()
        released = ProcessScopeLease(
            control_path=lease.control_path,
            lock_path=lease.lock_path,
            owner_token_sha256=lease.owner_token_sha256,
            pid=lease.pid,
            hostname=lease.hostname,
            acquired_at=lease.acquired_at,
            released=True,
        )
        self._lease = released
        self._owner_token = None
        return released

    @staticmethod
    def inspect_lock(
        control_path: str | Path,
    ) -> Mapping[str, Any] | None:
        path = Path(str(Path(control_path).resolve()) + ".process-scope.lock")
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_INVALID") from error
        if not isinstance(payload, dict):
            raise ValueError("PROCESS_SCOPE_GUARD_LOCK_INVALID")
        return payload


@dataclass(frozen=True)
class RunControlSnapshot:
    run_id: str
    manifest_fingerprint: str
    config_fingerprint: str
    provider_key: str
    subject_key: str
    modalities: tuple[str, ...]
    max_capture_rounds: int
    max_total_provider_calls: int
    max_runtime_ms: int
    state: str
    state_version: int
    created_at: datetime
    updated_at: datetime
    execution_authorized: bool = False
    production_admissible: bool = False

    def __post_init__(self) -> None:
        _sha256_hex(self.run_id, name="run_id")
        _sha256_hex(
            self.manifest_fingerprint,
            name="manifest_fingerprint",
        )
        _sha256_hex(
            self.config_fingerprint,
            name="config_fingerprint",
        )
        _nonempty(self.provider_key, name="provider_key")
        _nonempty(self.subject_key, name="subject_key")
        if self.state not in R8_2_RUN_STATES:
            raise ValueError("R8_2_RUN_STATE_INVALID")
        _nonnegative_int(self.state_version, name="state_version")
        object.__setattr__(
            self,
            "created_at",
            _aware_utc(self.created_at, name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _aware_utc(self.updated_at, name="updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ValueError("R8_2_RUN_CONTROL_TIME_REGRESSION")
        if self.execution_authorized is not False:
            raise ValueError("R8_2_EXECUTION_AUTHORIZATION_FORBIDDEN")
        if self.production_admissible is not False:
            raise ValueError("R8_2_PRODUCTION_ADMISSION_FORBIDDEN")


@dataclass(frozen=True)
class SequenceReservation:
    run_id: str
    round_index: int
    modality: str
    stream_key: str
    sequence_number: int
    state: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _sha256_hex(self.run_id, name="run_id")
        _positive_int(self.round_index, name="round_index")
        _nonempty(self.modality, name="modality")
        _nonempty(self.stream_key, name="stream_key")
        _positive_int(self.sequence_number, name="sequence_number")
        if self.state not in R8_2_RESERVATION_STATES:
            raise ValueError("R8_2_RESERVATION_STATE_INVALID")
        object.__setattr__(
            self,
            "created_at",
            _aware_utc(self.created_at, name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _aware_utc(self.updated_at, name="updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ValueError("R8_2_RESERVATION_TIME_REGRESSION")


class SQLiteBoundedFootballLiveControlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
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
        return connection

    @staticmethod
    def _stream_key(
        *,
        subject_key: str,
        provider_key: str,
        modality: str,
    ) -> str:
        return _sha(
            {
                "schema": "matrix.c2-r8-2-football-stream-key/1",
                "sport": "football",
                "subject_key": subject_key,
                "provider_key": provider_key,
                "modality": modality,
            }
        )

    def _anchor_payload(
        self,
        connection: sqlite3.Connection,
    ) -> Mapping[str, Any]:
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

        return {
            "schema": "matrix.c2-r8-2-control-anchor/1",
            "runs": [list(row) for row in run_rows],
            "streams": [list(row) for row in stream_rows],
            "reservations": [list(row) for row in reservation_rows],
        }

    def _anchor_payload_v82(
        self,
        connection: sqlite3.Connection,
    ) -> Mapping[str, Any]:
        run_rows = connection.execute(
            """
            SELECT
                run_id,
                manifest_fingerprint,
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

    def _rewrite_anchor(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        payload = self._anchor_payload(connection)
        payload_sha = _sha(payload)
        connection.execute(
            """
            INSERT INTO football_bounded_control_anchor (
                singleton_id,
                payload_sha256
            )
            VALUES (1, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET
                payload_sha256 = excluded.payload_sha256
            """,
            (payload_sha,),
        )

    def _assert_integrity(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if version != R8_2_CONTROL_LEDGER_USER_VERSION:
            raise ValueError("R8_2_CONTROL_SCHEMA_VERSION_MISMATCH")

        integrity = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        if integrity != "ok":
            raise ValueError("R8_2_SQLITE_INTEGRITY_CHECK_FAILED")

        anchor = connection.execute(
            """
            SELECT payload_sha256
            FROM football_bounded_control_anchor
            WHERE singleton_id = 1
            """
        ).fetchone()
        if anchor is None:
            raise ValueError("R8_2_CONTROL_ANCHOR_REQUIRED")

        expected_anchor = _sha(self._anchor_payload(connection))
        if str(anchor[0]) != expected_anchor:
            raise ValueError("R8_2_CONTROL_ANCHOR_MISMATCH")

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
            """
        ).fetchall()

        runs: dict[str, RunControlSnapshot] = {}
        for row in run_rows:
            modalities_raw = json.loads(str(row[5]))
            if not isinstance(modalities_raw, list):
                raise ValueError("R8_2_RUN_MODALITIES_LIST_REQUIRED")

            snapshot = RunControlSnapshot(
                run_id=str(row[0]),
                manifest_fingerprint=str(row[1]),
                config_fingerprint=str(row[2]),
                provider_key=str(row[3]),
                subject_key=str(row[4]),
                modalities=tuple(modalities_raw),
                max_capture_rounds=int(row[6]),
                max_total_provider_calls=int(row[7]),
                max_runtime_ms=int(row[8]),
                state=str(row[9]),
                state_version=int(row[10]),
                created_at=datetime.fromisoformat(str(row[11])),
                updated_at=datetime.fromisoformat(str(row[12])),
            )
            if len(set(snapshot.modalities)) != len(snapshot.modalities):
                raise ValueError("R8_2_DUPLICATE_RUN_MODALITY")

            rederived_config = BoundedFootballLiveExecutorConfig(
                provider_key=snapshot.provider_key,
                subject_key=snapshot.subject_key,
                modalities=snapshot.modalities,
                max_capture_rounds=snapshot.max_capture_rounds,
                max_total_provider_calls=snapshot.max_total_provider_calls,
                max_runtime_ms=snapshot.max_runtime_ms,
            )
            validate_r8_2_engineering_resource_ceiling_from_config(
                rederived_config
            )

            if (
                rederived_config.provider_key != snapshot.provider_key
                or rederived_config.subject_key != snapshot.subject_key
                or rederived_config.modalities != snapshot.modalities
            ):
                raise ValueError(
                    "R8_2_RUN_CONTROL_CANONICAL_CONFIG_MISMATCH"
                )
            if (
                rederived_config.config_fingerprint
                != snapshot.config_fingerprint
            ):
                raise ValueError(
                    "R8_2_RUN_CONTROL_CONFIG_FINGERPRINT_MISMATCH"
                )

            runs[snapshot.run_id] = snapshot

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
            """
        ).fetchall()

        max_by_stream: dict[str, int] = {}
        sequences_by_stream: dict[str, list[int]] = {}
        reservation_count_by_run: dict[str, int] = {}
        open_count_by_run: dict[str, int] = {}

        for row in reservation_rows:
            reservation = SequenceReservation(
                run_id=str(row[0]),
                round_index=int(row[1]),
                modality=str(row[2]),
                stream_key=str(row[3]),
                sequence_number=int(row[4]),
                state=str(row[5]),
                created_at=datetime.fromisoformat(str(row[6])),
                updated_at=datetime.fromisoformat(str(row[7])),
            )

            run = runs.get(reservation.run_id)
            if run is None:
                raise ValueError("R8_2_RESERVATION_RUN_NOT_FOUND")
            if reservation.modality not in run.modalities:
                raise ValueError(
                    "R8_2_RESERVATION_MODALITY_OUTSIDE_RUN_CONTRACT"
                )
            if reservation.round_index > run.max_capture_rounds:
                raise ValueError(
                    "R8_2_RESERVATION_ROUND_OUTSIDE_RUN_CONTRACT"
                )
            if reservation.created_at < run.created_at:
                raise ValueError(
                    "R8_2_RESERVATION_PRECEDES_RUN_REGISTRATION"
                )

            expected_stream_key = self._stream_key(
                subject_key=run.subject_key,
                provider_key=run.provider_key,
                modality=reservation.modality,
            )
            if reservation.stream_key != expected_stream_key:
                raise ValueError(
                    "R8_2_RESERVATION_STREAM_KEY_MISMATCH"
                )

            reservation_count_by_run[reservation.run_id] = (
                reservation_count_by_run.get(reservation.run_id, 0) + 1
            )
            if (
                reservation_count_by_run[reservation.run_id]
                > run.max_total_provider_calls
            ):
                raise ValueError(
                    "R8_2_RUN_PROVIDER_CALL_BUDGET_EXCEEDED"
                )

            if reservation.state == "RESERVED":
                open_count_by_run[reservation.run_id] = (
                    open_count_by_run.get(reservation.run_id, 0) + 1
                )

            sequences_by_stream.setdefault(
                reservation.stream_key,
                [],
            ).append(reservation.sequence_number)
            max_by_stream[reservation.stream_key] = max(
                max_by_stream.get(reservation.stream_key, 0),
                reservation.sequence_number,
            )

        for run_id, run in runs.items():
            open_count = open_count_by_run.get(run_id, 0)
            total_count = reservation_count_by_run.get(run_id, 0)

            if run.state == "PLANNED" and total_count != 0:
                raise ValueError(
                    "R8_2_PLANNED_RUN_WITH_RESERVATIONS_FORBIDDEN"
                )
            if run.state in {"COMPLETED", "ABORTED"} and open_count != 0:
                raise ValueError(
                    "R8_2_TERMINAL_RUN_WITH_OPEN_RESERVATIONS_FORBIDDEN"
                )

        for stream_key, sequences in sequences_by_stream.items():
            ordered = sorted(sequences)
            expected = list(range(1, ordered[-1] + 1))
            if ordered != expected:
                raise ValueError(
                    "R8_2_STREAM_SEQUENCE_CONTIGUITY_VIOLATION"
                )

        stream_rows = connection.execute(
            """
            SELECT stream_key, last_reserved_sequence
            FROM football_bounded_stream_sequence
            """
        ).fetchall()
        stream_state = {
            str(stream_key): int(last_sequence)
            for stream_key, last_sequence in stream_rows
        }

        if set(stream_state) != set(max_by_stream):
            raise ValueError("R8_2_STREAM_SEQUENCE_MEMBERSHIP_MISMATCH")
        for stream_key, maximum in max_by_stream.items():
            if stream_state[stream_key] != maximum:
                raise ValueError(
                    "R8_2_STREAM_SEQUENCE_WATERMARK_MISMATCH"
                )

    def _migrate_v82_to_v83(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        integrity = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        if integrity != "ok":
            raise ValueError("R8_2_SQLITE_INTEGRITY_CHECK_FAILED")

        anchor = connection.execute(
            """
            SELECT payload_sha256
            FROM football_bounded_control_anchor
            WHERE singleton_id = 1
            """
        ).fetchone()
        if anchor is None:
            raise ValueError("R8_2_CONTROL_ANCHOR_REQUIRED")

        expected_old_anchor = _sha(self._anchor_payload_v82(connection))
        if str(anchor[0]) != expected_old_anchor:
            raise ValueError("R8_2_V82_CONTROL_ANCHOR_MISMATCH")

        connection.execute(
            """
            ALTER TABLE football_bounded_run_control
            ADD COLUMN config_fingerprint TEXT
            """
        )

        rows = connection.execute(
            """
            SELECT
                run_id,
                provider_key,
                subject_key,
                modalities_json,
                max_capture_rounds,
                max_total_provider_calls,
                max_runtime_ms
            FROM football_bounded_run_control
            """
        ).fetchall()

        for row in rows:
            modalities = json.loads(str(row[3]))
            rederived = BoundedFootballLiveExecutorConfig(
                provider_key=str(row[1]),
                subject_key=str(row[2]),
                modalities=tuple(modalities),
                max_capture_rounds=int(row[4]),
                max_total_provider_calls=int(row[5]),
                max_runtime_ms=int(row[6]),
            )
            validate_r8_2_engineering_resource_ceiling_from_config(
                rederived
            )
            connection.execute(
                """
                UPDATE football_bounded_run_control
                SET config_fingerprint = ?
                WHERE run_id = ?
                """,
                (
                    rederived.config_fingerprint,
                    str(row[0]),
                ),
            )

        connection.execute(
            f"PRAGMA user_version = {R8_2_CONTROL_LEDGER_USER_VERSION}"
        )
        self._rewrite_anchor(connection)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = int(
                    connection.execute(
                        "PRAGMA user_version"
                    ).fetchone()[0]
                )
                if version not in (
                    0,
                    R8_2_PREVIOUS_CONTROL_LEDGER_USER_VERSION,
                    R8_2_CONTROL_LEDGER_USER_VERSION,
                ):
                    raise ValueError(
                        "R8_2_CONTROL_SCHEMA_VERSION_MISMATCH"
                    )

                if version == 0:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS
                        football_bounded_run_control (
                            run_id TEXT PRIMARY KEY,
                            manifest_fingerprint TEXT NOT NULL,
                            config_fingerprint TEXT NOT NULL,
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
                        )
                        """
                    )
                else:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS
                        football_bounded_run_control (
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
                        )
                        """
                    )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    football_bounded_stream_sequence (
                        stream_key TEXT PRIMARY KEY,
                        last_reserved_sequence INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    football_bounded_sequence_reservation (
                        run_id TEXT NOT NULL,
                        round_index INTEGER NOT NULL,
                        modality TEXT NOT NULL,
                        stream_key TEXT NOT NULL,
                        sequence_number INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (
                            run_id,
                            round_index,
                            modality
                        ),
                        UNIQUE (
                            stream_key,
                            sequence_number
                        ),
                        FOREIGN KEY (run_id)
                            REFERENCES football_bounded_run_control(run_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    football_bounded_control_anchor (
                        singleton_id INTEGER PRIMARY KEY
                            CHECK (singleton_id = 1),
                        payload_sha256 TEXT NOT NULL
                    )
                    """
                )

                if version == R8_2_PREVIOUS_CONTROL_LEDGER_USER_VERSION:
                    self._migrate_v82_to_v83(connection)
                    version = R8_2_CONTROL_LEDGER_USER_VERSION
                elif version == 0:
                    connection.execute(
                        f"PRAGMA user_version = {R8_2_CONTROL_LEDGER_USER_VERSION}"
                    )
                    version = R8_2_CONTROL_LEDGER_USER_VERSION

                anchor = connection.execute(
                    """
                    SELECT 1
                    FROM football_bounded_control_anchor
                    WHERE singleton_id = 1
                    """
                ).fetchone()

                has_rows = any(
                    int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                    )
                    > 0
                    for table in (
                        "football_bounded_run_control",
                        "football_bounded_stream_sequence",
                        "football_bounded_sequence_reservation",
                    )
                )

                if anchor is None:
                    if has_rows:
                        raise ValueError("R8_2_CONTROL_ANCHOR_REQUIRED")
                    self._rewrite_anchor(connection)
                else:
                    self._assert_integrity(connection)

                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _assert_guard(
        self,
        guard: BoundedExecutorProcessScopeGuard,
        lease: ProcessScopeLease,
    ) -> None:
        if guard.control_path != self.path:
            raise ValueError("R8_2_PROCESS_GUARD_PATH_MISMATCH")
        guard.assert_active(lease)

    def register_run(
        self,
        manifest: BoundedFootballLiveRunManifest,
        *,
        guard: BoundedExecutorProcessScopeGuard,
        lease: ProcessScopeLease,
        registered_at: datetime,
    ) -> RunControlSnapshot:
        self._assert_guard(guard, lease)
        validate_r8_2_engineering_resource_ceiling(manifest)
        registered = _aware_utc(
            registered_at,
            name="registered_at",
        )
        if registered < manifest.created_at:
            raise ValueError(
                "R8_2_RUN_REGISTRATION_PRECEDES_MANIFEST_CREATION"
            )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT
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
                    WHERE run_id = ?
                    """,
                    (manifest.run_id,),
                ).fetchone()

                modalities_json = json.dumps(
                    list(manifest.modalities),
                    separators=(",", ":"),
                    ensure_ascii=False,
                )

                if row is None:
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
                            manifest.run_id,
                            manifest.manifest_fingerprint,
                            manifest.config_fingerprint,
                            manifest.provider_key,
                            manifest.subject_key,
                            modalities_json,
                            manifest.max_capture_rounds,
                            manifest.max_total_provider_calls,
                            manifest.max_runtime_ms,
                            "PLANNED",
                            0,
                            registered.isoformat(),
                            registered.isoformat(),
                        ),
                    )
                else:
                    immutable = (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        int(row[5]),
                        int(row[6]),
                        int(row[7]),
                    )
                    expected = (
                        manifest.manifest_fingerprint,
                        manifest.config_fingerprint,
                        manifest.provider_key,
                        manifest.subject_key,
                        modalities_json,
                        manifest.max_capture_rounds,
                        manifest.max_total_provider_calls,
                        manifest.max_runtime_ms,
                    )
                    if immutable != expected:
                        raise ValueError(
                            "R8_2_RUN_CONTROL_IMMUTABLE_MANIFEST_MISMATCH"
                        )

                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return self.get_run(manifest.run_id)

    def get_run(
        self,
        run_id: str,
    ) -> RunControlSnapshot:
        normalized = _sha256_hex(run_id, name="run_id")
        with self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
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
                WHERE run_id = ?
                """,
                (normalized,),
            ).fetchone()

        if row is None:
            raise ValueError("R8_2_RUN_CONTROL_NOT_FOUND")

        return RunControlSnapshot(
            run_id=str(row[0]),
            manifest_fingerprint=str(row[1]),
            config_fingerprint=str(row[2]),
            provider_key=str(row[3]),
            subject_key=str(row[4]),
            modalities=tuple(json.loads(str(row[5]))),
            max_capture_rounds=int(row[6]),
            max_total_provider_calls=int(row[7]),
            max_runtime_ms=int(row[8]),
            state=str(row[9]),
            state_version=int(row[10]),
            created_at=datetime.fromisoformat(str(row[11])),
            updated_at=datetime.fromisoformat(str(row[12])),
        )

    def transition_run_state(
        self,
        run_id: str,
        *,
        expected_state: str,
        expected_state_version: int,
        new_state: str,
        changed_at: datetime,
        guard: BoundedExecutorProcessScopeGuard,
        lease: ProcessScopeLease,
    ) -> RunControlSnapshot:
        self._assert_guard(guard, lease)
        normalized = _sha256_hex(run_id, name="run_id")
        if expected_state not in R8_2_RUN_STATES:
            raise ValueError("R8_2_EXPECTED_RUN_STATE_INVALID")
        if new_state not in R8_2_RUN_STATES:
            raise ValueError("R8_2_NEW_RUN_STATE_INVALID")
        if new_state not in _R8_2_ALLOWED_TRANSITIONS[expected_state]:
            raise ValueError("R8_2_RUN_STATE_TRANSITION_FORBIDDEN")
        version = _nonnegative_int(
            expected_state_version,
            name="expected_state_version",
        )
        changed = _aware_utc(changed_at, name="changed_at")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT state, state_version, created_at, updated_at
                    FROM football_bounded_run_control
                    WHERE run_id = ?
                    """,
                    (normalized,),
                ).fetchone()
                if row is None:
                    raise ValueError("R8_2_RUN_CONTROL_NOT_FOUND")
                if str(row[0]) != expected_state:
                    raise ValueError("R8_2_RUN_STATE_COMPARE_AND_SWAP_FAILED")
                if int(row[1]) != version:
                    raise ValueError(
                        "R8_2_RUN_STATE_VERSION_COMPARE_AND_SWAP_FAILED"
                    )

                current_updated_at = datetime.fromisoformat(str(row[3]))
                if changed < current_updated_at:
                    raise ValueError("R8_2_RUN_TIME_REGRESSION")

                latest_reservation_row = connection.execute(
                    """
                    SELECT MAX(updated_at)
                    FROM football_bounded_sequence_reservation
                    WHERE run_id = ?
                    """,
                    (normalized,),
                ).fetchone()
                if (
                    latest_reservation_row is not None
                    and latest_reservation_row[0] is not None
                ):
                    latest_reservation_at = datetime.fromisoformat(
                        str(latest_reservation_row[0])
                    )
                    if changed < latest_reservation_at:
                        raise ValueError(
                            "R8_2_RUN_TIME_PRECEDES_RESERVATION"
                        )

                if new_state == "COMPLETED":
                    open_reservations = int(
                        connection.execute(
                            """
                            SELECT COUNT(*)
                            FROM football_bounded_sequence_reservation
                            WHERE run_id = ?
                              AND state = 'RESERVED'
                            """,
                            (normalized,),
                        ).fetchone()[0]
                    )
                    if open_reservations != 0:
                        raise ValueError(
                            "R8_2_COMPLETION_WITH_OPEN_RESERVATIONS_FORBIDDEN"
                        )

                if new_state == "ABORTED":
                    connection.execute(
                        """
                        UPDATE football_bounded_sequence_reservation
                        SET state = 'ABANDONED',
                            updated_at = ?
                        WHERE run_id = ?
                          AND state = 'RESERVED'
                        """,
                        (
                            changed.isoformat(),
                            normalized,
                        ),
                    )

                connection.execute(
                    """
                    UPDATE football_bounded_run_control
                    SET state = ?,
                        state_version = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        new_state,
                        version + 1,
                        changed.isoformat(),
                        normalized,
                    ),
                )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return self.get_run(normalized)

    def reserve_next_sequence(
        self,
        run_id: str,
        *,
        round_index: int,
        modality: str,
        reserved_at: datetime,
        guard: BoundedExecutorProcessScopeGuard,
        lease: ProcessScopeLease,
    ) -> SequenceReservation:
        self._assert_guard(guard, lease)
        normalized = _sha256_hex(run_id, name="run_id")
        round_number = _positive_int(
            round_index,
            name="round_index",
        )
        modality_value = _nonempty(modality, name="modality")
        reserved = _aware_utc(reserved_at, name="reserved_at")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                run = connection.execute(
                    """
                    SELECT
                        provider_key,
                        subject_key,
                        modalities_json,
                        max_capture_rounds,
                        max_total_provider_calls,
                        state,
                        created_at,
                        updated_at
                    FROM football_bounded_run_control
                    WHERE run_id = ?
                    """,
                    (normalized,),
                ).fetchone()
                if run is None:
                    raise ValueError("R8_2_RUN_CONTROL_NOT_FOUND")
                if str(run[5]) != "IN_PROGRESS":
                    raise ValueError(
                        "R8_2_SEQUENCE_RESERVATION_REQUIRES_IN_PROGRESS_RUN"
                    )

                run_updated_at = datetime.fromisoformat(str(run[7]))
                if reserved < run_updated_at:
                    raise ValueError(
                        "R8_2_RESERVATION_TIME_PRECEDES_RUN_STATE"
                    )

                modalities = tuple(json.loads(str(run[2])))
                if modality_value not in modalities:
                    raise ValueError("R8_2_RUN_MODALITY_NOT_ALLOWED")
                if round_number > int(run[3]):
                    raise ValueError("R8_2_ROUND_INDEX_EXCEEDS_RUN_BOUND")

                existing = connection.execute(
                    """
                    SELECT
                        stream_key,
                        sequence_number,
                        state,
                        created_at,
                        updated_at
                    FROM football_bounded_sequence_reservation
                    WHERE run_id = ?
                      AND round_index = ?
                      AND modality = ?
                    """,
                    (
                        normalized,
                        round_number,
                        modality_value,
                    ),
                ).fetchone()
                if existing is not None:
                    connection.execute("COMMIT")
                    return SequenceReservation(
                        run_id=normalized,
                        round_index=round_number,
                        modality=modality_value,
                        stream_key=str(existing[0]),
                        sequence_number=int(existing[1]),
                        state=str(existing[2]),
                        created_at=datetime.fromisoformat(str(existing[3])),
                        updated_at=datetime.fromisoformat(str(existing[4])),
                    )

                reservation_count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM football_bounded_sequence_reservation
                        WHERE run_id = ?
                        """,
                        (normalized,),
                    ).fetchone()[0]
                )
                if reservation_count >= int(run[4]):
                    raise ValueError("R8_2_RUN_PROVIDER_CALL_BUDGET_EXHAUSTED")

                stream_key = self._stream_key(
                    subject_key=str(run[1]),
                    provider_key=str(run[0]),
                    modality=modality_value,
                )
                state_row = connection.execute(
                    """
                    SELECT last_reserved_sequence
                    FROM football_bounded_stream_sequence
                    WHERE stream_key = ?
                    """,
                    (stream_key,),
                ).fetchone()
                next_sequence = (
                    1 if state_row is None else int(state_row[0]) + 1
                )

                if state_row is None:
                    connection.execute(
                        """
                        INSERT INTO football_bounded_stream_sequence (
                            stream_key,
                            last_reserved_sequence
                        )
                        VALUES (?, ?)
                        """,
                        (stream_key, next_sequence),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE football_bounded_stream_sequence
                        SET last_reserved_sequence = ?
                        WHERE stream_key = ?
                        """,
                        (next_sequence, stream_key),
                    )

                connection.execute(
                    """
                    INSERT INTO football_bounded_sequence_reservation (
                        run_id,
                        round_index,
                        modality,
                        stream_key,
                        sequence_number,
                        state,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized,
                        round_number,
                        modality_value,
                        stream_key,
                        next_sequence,
                        "RESERVED",
                        reserved.isoformat(),
                        reserved.isoformat(),
                    ),
                )

                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return SequenceReservation(
            run_id=normalized,
            round_index=round_number,
            modality=modality_value,
            stream_key=stream_key,
            sequence_number=next_sequence,
            state="RESERVED",
            created_at=reserved,
            updated_at=reserved,
        )

    def transition_reservation(
        self,
        run_id: str,
        *,
        round_index: int,
        modality: str,
        expected_state: str,
        new_state: str,
        changed_at: datetime,
        guard: BoundedExecutorProcessScopeGuard,
        lease: ProcessScopeLease,
    ) -> SequenceReservation:
        self._assert_guard(guard, lease)
        normalized = _sha256_hex(run_id, name="run_id")
        round_number = _positive_int(
            round_index,
            name="round_index",
        )
        modality_value = _nonempty(modality, name="modality")
        changed = _aware_utc(changed_at, name="changed_at")

        if expected_state != "RESERVED":
            raise ValueError("R8_2_RESERVATION_EXPECTED_STATE_INVALID")
        if new_state not in {"COMMITTED", "ABANDONED"}:
            raise ValueError("R8_2_RESERVATION_TRANSITION_FORBIDDEN")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT
                        stream_key,
                        sequence_number,
                        state,
                        created_at,
                        updated_at
                    FROM football_bounded_sequence_reservation
                    WHERE run_id = ?
                      AND round_index = ?
                      AND modality = ?
                    """,
                    (
                        normalized,
                        round_number,
                        modality_value,
                    ),
                ).fetchone()
                if row is None:
                    raise ValueError("R8_2_SEQUENCE_RESERVATION_NOT_FOUND")

                run_row = connection.execute(
                    """
                    SELECT state, updated_at
                    FROM football_bounded_run_control
                    WHERE run_id = ?
                    """,
                    (normalized,),
                ).fetchone()
                if run_row is None:
                    raise ValueError("R8_2_RUN_CONTROL_NOT_FOUND")
                if str(run_row[0]) not in {"IN_PROGRESS", "RECOVERY_REQUIRED"}:
                    raise ValueError(
                        "R8_2_RESERVATION_TRANSITION_RUN_STATE_FORBIDDEN"
                    )

                current_updated_at = datetime.fromisoformat(str(row[4]))
                run_updated_at = datetime.fromisoformat(str(run_row[1]))
                if changed < current_updated_at:
                    raise ValueError(
                        "R8_2_RESERVATION_TIME_REGRESSION"
                    )
                if changed < run_updated_at:
                    raise ValueError(
                        "R8_2_RESERVATION_TIME_PRECEDES_RUN_STATE"
                    )

                current_state = str(row[2])
                if current_state == new_state:
                    connection.execute("COMMIT")
                    return SequenceReservation(
                        run_id=normalized,
                        round_index=round_number,
                        modality=modality_value,
                        stream_key=str(row[0]),
                        sequence_number=int(row[1]),
                        state=current_state,
                        created_at=datetime.fromisoformat(str(row[3])),
                        updated_at=datetime.fromisoformat(str(row[4])),
                    )
                if current_state != expected_state:
                    raise ValueError(
                        "R8_2_RESERVATION_STATE_COMPARE_AND_SWAP_FAILED"
                    )

                connection.execute(
                    """
                    UPDATE football_bounded_sequence_reservation
                    SET state = ?,
                        updated_at = ?
                    WHERE run_id = ?
                      AND round_index = ?
                      AND modality = ?
                    """,
                    (
                        new_state,
                        changed.isoformat(),
                        normalized,
                        round_number,
                        modality_value,
                    ),
                )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return self.get_reservation(
            normalized,
            round_index=round_number,
            modality=modality_value,
        )

    def get_reservation(
        self,
        run_id: str,
        *,
        round_index: int,
        modality: str,
    ) -> SequenceReservation:
        normalized = _sha256_hex(run_id, name="run_id")
        round_number = _positive_int(
            round_index,
            name="round_index",
        )
        modality_value = _nonempty(modality, name="modality")

        with self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
                """
                SELECT
                    stream_key,
                    sequence_number,
                    state,
                    created_at,
                    updated_at
                FROM football_bounded_sequence_reservation
                WHERE run_id = ?
                  AND round_index = ?
                  AND modality = ?
                """,
                (
                    normalized,
                    round_number,
                    modality_value,
                ),
            ).fetchone()

        if row is None:
            raise ValueError("R8_2_SEQUENCE_RESERVATION_NOT_FOUND")

        return SequenceReservation(
            run_id=normalized,
            round_index=round_number,
            modality=modality_value,
            stream_key=str(row[0]),
            sequence_number=int(row[1]),
            state=str(row[2]),
            created_at=datetime.fromisoformat(str(row[3])),
            updated_at=datetime.fromisoformat(str(row[4])),
        )

    def audit_integrity(self) -> bool:
        try:
            with self._connect() as connection:
                self._assert_integrity(connection)
            return True
        except (
            ValueError,
            sqlite3.Error,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ):
            return False
