from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER = "APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER"
APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN = "APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN"
TAIL_GUARD_INITIALIZATION_STATE_REQUIRED = "TAIL_GUARD_INITIALIZATION_STATE_REQUIRED"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AppendOnlyTailGuardIntegrityReport:
    ok: bool
    protected_records: int
    commitments: int
    sequence_high_water: int
    errors: tuple[str, ...]


class SQLiteAppendOnlyTailGuard:
    def __init__(self, *, table_name: str, ledger_name: str) -> None:
        if not isinstance(table_name, str) or _IDENTIFIER.fullmatch(table_name) is None:
            raise ValueError("TAIL_GUARD_TABLE_NAME_INVALID")
        if not isinstance(ledger_name, str) or not ledger_name.strip():
            raise ValueError("TAIL_GUARD_LEDGER_NAME_REQUIRED")
        self.table_name = table_name
        self.ledger_name = ledger_name.strip()
        self.state_table_name = table_name + "_state"
        if _IDENTIFIER.fullmatch(self.state_table_name) is None:
            raise ValueError("TAIL_GUARD_STATE_TABLE_NAME_INVALID")
        self._baseline_valid = True
        self._schema_observed = False
        self._guard_preexisted = False
        self._state_preexisted = False

    def _state_marker_sha256(self) -> str:
        return _sha({
            "schema": "matrix.append-only-tail-guard-state/1",
            "ledger_name": self.ledger_name,
            "guard_table_name": self.table_name,
        })


    def _table_exists(self, connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _database_path(self, connection) -> Path | None:
        for row in connection.execute("PRAGMA database_list").fetchall():
            if len(row) >= 3 and str(row[1]) == "main":
                raw = str(row[2]).strip()
                return None if not raw else Path(raw).resolve()
        return None

    def _external_anchor_path(self, connection) -> Path | None:
        database_path = self._database_path(connection)
        if database_path is None:
            return None
        return Path(
            str(database_path)
            + "."
            + self.table_name
            + ".init-anchor"
        )

    def _external_anchor_text(self) -> str:
        return _canonical_json({
            "schema": "matrix.append-only-tail-guard-external-anchor/1",
            "ledger_name": self.ledger_name,
            "guard_table_name": self.table_name,
            "initialization_marker_sha256": self._state_marker_sha256(),
        })

    def _external_anchor_status(self, connection) -> str:
        path = self._external_anchor_path(connection)
        if path is None:
            return "NOT_APPLICABLE"
        if not path.exists():
            return "MISSING"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return "INVALID"
        return "VALID" if text == self._external_anchor_text() else "INVALID"

    def _write_external_anchor(self, connection) -> None:
        path = self._external_anchor_path(connection)
        if path is None:
            return

        expected = self._external_anchor_text()

        if path.exists():
            if path.read_text(encoding="utf-8") != expected:
                raise ValueError(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID)
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(expected)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if path.read_text(encoding="utf-8") != expected:
                raise ValueError(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID)

    def ensure_schema(self, connection) -> None:
        if not self._schema_observed:
            self._guard_preexisted = self._table_exists(connection, self.table_name)
            self._state_preexisted = self._table_exists(connection, self.state_table_name)
            self._schema_observed = True

        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
            "sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "record_id TEXT NOT NULL UNIQUE,"
            "record_payload_sha256 TEXT NOT NULL,"
            "previous_commitment_sha256 TEXT,"
            "commitment_sha256 TEXT NOT NULL UNIQUE)"
        )
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {self.state_table_name} ("
            "ledger_name TEXT PRIMARY KEY,"
            "guard_table_name TEXT NOT NULL UNIQUE,"
            "initialization_marker_sha256 TEXT NOT NULL)"
        )

    def _state_row(self, connection):
        return connection.execute(
            f"SELECT guard_table_name, initialization_marker_sha256 "
            f"FROM {self.state_table_name} WHERE ledger_name = ?",
            (self.ledger_name,),
        ).fetchone()

    def _state_is_valid(self, connection) -> bool:
        row = self._state_row(connection)
        if row is None:
            return False
        return (
            str(row[0]) == self.table_name
            and str(row[1]) == self._state_marker_sha256()
        )

    def _sequence_high_water(self, connection) -> int:
        row = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = ?",
            (self.table_name,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def _last_commitment(self, connection) -> tuple[int, str | None]:
        row = connection.execute(
            f"SELECT sequence_id, commitment_sha256 FROM {self.table_name} "
            "ORDER BY sequence_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0, None
        return int(row[0]), str(row[1])

    def _append_unchecked(self, connection, *, record_id: str, record_payload_sha256: str) -> None:
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("TAIL_GUARD_RECORD_ID_REQUIRED")
        if not isinstance(record_payload_sha256, str) or len(record_payload_sha256) != 64:
            raise ValueError("TAIL_GUARD_RECORD_HASH_INVALID")

        last_sequence, previous_hash = self._last_commitment(connection)
        high_water = self._sequence_high_water(connection)
        if high_water != last_sequence:
            raise ValueError("APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER_MISMATCH")

        sequence_id = last_sequence + 1
        payload = {
            "schema": "matrix.append-only-tail-guard/1",
            "ledger_name": self.ledger_name,
            "sequence_id": sequence_id,
            "record_id": record_id.strip(),
            "record_payload_sha256": record_payload_sha256,
            "previous_commitment_sha256": previous_hash,
        }
        commitment_sha256 = _sha(payload)
        connection.execute(
            f"INSERT INTO {self.table_name} "
            "(sequence_id, record_id, record_payload_sha256, previous_commitment_sha256, commitment_sha256) "
            "VALUES (?, ?, ?, ?, ?)",
            (sequence_id, record_id.strip(), record_payload_sha256, previous_hash, commitment_sha256),
        )

    def _audit_core(self, connection, protected: tuple[tuple[str, str], ...]) -> AppendOnlyTailGuardIntegrityReport:
        guard_rows = connection.execute(
            f"SELECT sequence_id, record_id, record_payload_sha256, previous_commitment_sha256, commitment_sha256 "
            f"FROM {self.table_name} ORDER BY sequence_id"
        ).fetchall()
        errors: list[str] = []
        high_water = self._sequence_high_water(connection)

        state_row = self._state_row(connection)
        if state_row is None:
            errors.append("TAIL_GUARD_INITIALIZATION_STATE_MISSING")
        elif not self._state_is_valid(connection):
            errors.append("TAIL_GUARD_INITIALIZATION_STATE_INVALID")

        anchor_status = self._external_anchor_status(connection)
        if anchor_status == "MISSING":
            errors.append(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED)
        elif anchor_status == "INVALID":
            errors.append(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID)

        if len(protected) != len(guard_rows):
            errors.append("TAIL_GUARD_RECORD_COUNT_MISMATCH")

        expected_previous: str | None = None
        guarded_records: dict[str, str] = {}
        for expected_sequence, row in enumerate(guard_rows, start=1):
            sequence_id, record_id, payload_sha, previous_sha, commitment_sha = row
            sequence_id = int(sequence_id)
            record_id = str(record_id)
            payload_sha = str(payload_sha)
            previous_sha = None if previous_sha is None else str(previous_sha)
            commitment_sha = str(commitment_sha)

            if sequence_id != expected_sequence:
                errors.append("TAIL_GUARD_SEQUENCE_GAP:" + str(sequence_id))
            if previous_sha != expected_previous:
                errors.append("TAIL_GUARD_CHAIN_MISMATCH:" + record_id)

            payload = {
                "schema": "matrix.append-only-tail-guard/1",
                "ledger_name": self.ledger_name,
                "sequence_id": sequence_id,
                "record_id": record_id,
                "record_payload_sha256": payload_sha,
                "previous_commitment_sha256": previous_sha,
            }
            if _sha(payload) != commitment_sha:
                errors.append("TAIL_GUARD_COMMITMENT_HASH_MISMATCH:" + record_id)
            guarded_records[record_id] = payload_sha
            expected_previous = commitment_sha

        last_sequence = int(guard_rows[-1][0]) if guard_rows else 0
        if high_water != last_sequence:
            errors.append("APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER_MISMATCH")

        protected_records = {record_id: payload_sha for record_id, payload_sha in protected}
        if protected_records != guarded_records:
            errors.append("TAIL_GUARD_RECORD_SET_MISMATCH")

        if state_row is not None and protected and not guard_rows and high_water == 0:
            errors.append(APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN)

        return AppendOnlyTailGuardIntegrityReport(
            ok=not errors,
            protected_records=len(protected),
            commitments=len(guard_rows),
            sequence_high_water=high_water,
            errors=tuple(errors),
        )

    def append(self, connection, *, record_id: str, record_payload_sha256: str) -> None:
        self.ensure_schema(connection)
        if not self._baseline_valid:
            raise ValueError(APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN)
        if not self._state_is_valid(connection):
            raise ValueError(TAIL_GUARD_INITIALIZATION_STATE_REQUIRED)

        anchor_status = self._external_anchor_status(connection)
        if anchor_status == "MISSING":
            raise ValueError(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED)
        if anchor_status == "INVALID":
            raise ValueError(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID)

        existing = connection.execute(
            f"SELECT record_payload_sha256 FROM {self.table_name} WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != record_payload_sha256:
                raise ValueError("TAIL_GUARD_RECORD_MUTATION_VIOLATION")
            return
        self._append_unchecked(
            connection,
            record_id=record_id,
            record_payload_sha256=record_payload_sha256,
        )

    def bootstrap_if_pristine(self, connection, *, records: Iterable[tuple[str, str]]) -> None:
        self.ensure_schema(connection)
        rows = tuple((str(record_id), str(payload_sha)) for record_id, payload_sha in records)
        anchor_status = self._external_anchor_status(connection)

        if anchor_status == "INVALID":
            self._baseline_valid = False
            raise ValueError(APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_INVALID)

        state_row = self._state_row(connection)

        if state_row is not None:
            report = self._audit_core(connection, rows)
            self._baseline_valid = report.ok
            if not report.ok:
                return
            if anchor_status == "MISSING":
                self._write_external_anchor(connection)
            return

        if anchor_status == "VALID":
            self._baseline_valid = False
            raise ValueError(APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN)

        guard_count = int(connection.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0])
        high_water = self._sequence_high_water(connection)

        if rows and not self._guard_preexisted and not self._state_preexisted:
            self._baseline_valid = False
            raise ValueError(APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN)

        if guard_count == 0 and high_water == 0:
            for record_id, payload_sha in rows:
                self._append_unchecked(
                    connection,
                    record_id=record_id,
                    record_payload_sha256=payload_sha,
                )
        else:
            # Upgrade from the immediately preceding guard version: only adopt
            # an existing baseline if it exactly matches the durable records.
            temporary_state_marker = self._state_marker_sha256()
            connection.execute(
                f"INSERT INTO {self.state_table_name} "
                "(ledger_name, guard_table_name, initialization_marker_sha256) "
                "VALUES (?, ?, ?)",
                (self.ledger_name, self.table_name, temporary_state_marker),
            )
            report = self._audit_core(connection, rows)
            if not report.ok:
                raise ValueError("TAIL_GUARD_EXISTING_BASELINE_INVALID")
            self._write_external_anchor(connection)
            self._baseline_valid = True
            return

        connection.execute(
            f"INSERT INTO {self.state_table_name} "
            "(ledger_name, guard_table_name, initialization_marker_sha256) "
            "VALUES (?, ?, ?)",
            (self.ledger_name, self.table_name, self._state_marker_sha256()),
        )
        self._write_external_anchor(connection)
        self._baseline_valid = True

    def audit(self, connection, *, records: Iterable[tuple[str, str]]) -> AppendOnlyTailGuardIntegrityReport:
        self.ensure_schema(connection)
        protected = tuple((str(record_id), str(payload_sha)) for record_id, payload_sha in records)
        report = self._audit_core(connection, protected)
        self._baseline_valid = report.ok
        return report
