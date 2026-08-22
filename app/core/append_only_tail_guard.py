from __future__ import annotations

from uuid import uuid4

from app.core.freshness_root import (
    FreshnessReservation,
    FreshnessRoot,
    FreshnessState,
    require_production_authorized,
)

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
APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_REQUIRED = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_REQUIRED"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_INVALID = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_INVALID"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_ROLLBACK = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_ROLLBACK"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_DIVERGENCE = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_DIVERGENCE"
APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_NOT_CURRENT = "APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_NOT_CURRENT"


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
    def __init__(
        self,
        *,
        table_name: str,
        ledger_name: str,
        freshness_root: FreshnessRoot | None = None,
        freshness_scope_id: str | None = None,
        require_production_freshness_root: bool = False,
    ) -> None:
        if not isinstance(table_name, str) or _IDENTIFIER.fullmatch(table_name) is None:
            raise ValueError("TAIL_GUARD_TABLE_NAME_INVALID")
        if not isinstance(ledger_name, str) or not ledger_name.strip():
            raise ValueError("TAIL_GUARD_LEDGER_NAME_REQUIRED")
        if (
            freshness_root is not None
            and (
                not isinstance(freshness_scope_id, str)
                or not freshness_scope_id.strip()
            )
        ):
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_FRESHNESS_SCOPE_REQUIRED"
            )
        if (
            require_production_freshness_root
            and freshness_root is None
        ):
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_FRESHNESS_ROOT_REQUIRED"
            )
        if require_production_freshness_root:
            assert freshness_root is not None
            require_production_authorized(
                freshness_root
            )

        self.table_name = table_name
        self.ledger_name = ledger_name.strip()
        self.state_table_name = table_name + "_state"

        if _IDENTIFIER.fullmatch(self.state_table_name) is None:
            raise ValueError("TAIL_GUARD_STATE_TABLE_NAME_INVALID")

        self.freshness_root = freshness_root
        self.freshness_scope_id = (
            freshness_scope_id.strip()
            if isinstance(freshness_scope_id, str)
            and freshness_scope_id.strip()
            else None
        )
        self.require_production_freshness_root = (
            require_production_freshness_root
        )

        if self.freshness_scope_id is None:
            self.freshness_namespace = (
                "matrix.append-only-tail-guard/"
                + self.ledger_name
                + "/"
                + self.table_name
            )
        else:
            self.freshness_namespace = (
                "matrix.append-only-tail-guard/"
                + self.freshness_scope_id
                + "/"
                + self.ledger_name
                + "/"
                + self.table_name
            )

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

    def _external_checkpoint_path(self, connection) -> Path | None:
        database_path = self._database_path(connection)

        if database_path is None:
            return None

        return Path(
            str(database_path)
            + "."
            + self.table_name
            + ".tail-checkpoint"
        )

    def _current_tail_checkpoint(
        self,
        connection,
    ) -> tuple[int, str | None]:
        row = connection.execute(
            f"SELECT sequence_id, commitment_sha256 "
            f"FROM {self.table_name} "
            f"ORDER BY sequence_id DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return (0, None)

        return (
            int(row[0]),
            str(row[1]),
        )

    def _external_checkpoint_text(
        self,
        *,
        sequence_id: int,
        commitment_sha256: str | None,
    ) -> str:
        return _canonical_json({
            "schema": (
                "matrix.append-only-tail-guard-"
                "external-checkpoint/1"
            ),
            "ledger_name": self.ledger_name,
            "guard_table_name": self.table_name,
            "initialization_marker_sha256": (
                self._state_marker_sha256()
            ),
            "sequence_id": sequence_id,
            "commitment_sha256": commitment_sha256,
        })

    def _external_checkpoint_status(
        self,
        connection,
    ) -> tuple[
        str,
        tuple[int, str | None] | None,
    ]:
        path = self._external_checkpoint_path(connection)

        if path is None:
            return ("NOT_APPLICABLE", None)

        if not path.exists():
            return ("MISSING", None)

        try:
            text = path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(text)
        except (OSError, ValueError, TypeError):
            return ("INVALID", None)

        if type(payload) is not dict:
            return ("INVALID", None)

        expected_keys = {
            "schema",
            "ledger_name",
            "guard_table_name",
            "initialization_marker_sha256",
            "sequence_id",
            "commitment_sha256",
        }

        if set(payload) != expected_keys:
            return ("INVALID", None)

        if payload.get("schema") != (
            "matrix.append-only-tail-guard-"
            "external-checkpoint/1"
        ):
            return ("INVALID", None)

        if payload.get("ledger_name") != self.ledger_name:
            return ("INVALID", None)

        if payload.get("guard_table_name") != self.table_name:
            return ("INVALID", None)

        if payload.get(
            "initialization_marker_sha256"
        ) != self._state_marker_sha256():
            return ("INVALID", None)

        sequence_id = payload.get(
            "sequence_id"
        )

        if (
            type(sequence_id) is not int
            or sequence_id < 0
        ):
            return ("INVALID", None)

        commitment = payload.get(
            "commitment_sha256"
        )

        if sequence_id == 0:
            if commitment is not None:
                return ("INVALID", None)
        else:
            if (
                not isinstance(commitment, str)
                or re.fullmatch(
                    r"[0-9a-f]{64}",
                    commitment,
                )
                is None
            ):
                return ("INVALID", None)

        expected_text = self._external_checkpoint_text(
            sequence_id=sequence_id,
            commitment_sha256=commitment,
        )

        if text != expected_text:
            return ("INVALID", None)

        return (
            "VALID",
            (
                sequence_id,
                commitment,
            ),
        )

    def _external_checkpoint_relation(
        self,
        connection,
    ) -> str:
        status, checkpoint = (
            self._external_checkpoint_status(
                connection
            )
        )

        if status != "VALID":
            return status

        assert checkpoint is not None

        external_sequence, external_commitment = (
            checkpoint
        )

        current_sequence, current_commitment = (
            self._current_tail_checkpoint(
                connection
            )
        )

        if external_sequence > current_sequence:
            return "ROLLBACK"

        if external_sequence == current_sequence:
            if (
                external_commitment
                == current_commitment
            ):
                return "MATCH"

            return "DIVERGENCE"

        if external_sequence == 0:
            if external_commitment is None:
                return "BEHIND"

            return "DIVERGENCE"

        row = connection.execute(
            f"SELECT commitment_sha256 "
            f"FROM {self.table_name} "
            f"WHERE sequence_id = ?",
            (external_sequence,),
        ).fetchone()

        if row is None:
            return "DIVERGENCE"

        if (
            str(row[0])
            != external_commitment
        ):
            return "DIVERGENCE"

        return "BEHIND"

    def _raise_for_external_checkpoint_relation(
        self,
        relation: str,
        *,
        allow_behind: bool,
    ) -> None:
        if relation in {
            "NOT_APPLICABLE",
            "MATCH",
        }:
            return

        if (
            relation == "BEHIND"
            and allow_behind
        ):
            return

        self._baseline_valid = False

        if relation == "MISSING":
            raise ValueError(
                APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_REQUIRED
            )

        if relation == "INVALID":
            raise ValueError(
                APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_INVALID
            )

        if relation == "ROLLBACK":
            raise ValueError(
                APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_ROLLBACK
            )

        if relation == "DIVERGENCE":
            raise ValueError(
                APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_DIVERGENCE
            )

        if relation == "BEHIND":
            raise ValueError(
                APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_NOT_CURRENT
            )

        raise ValueError(
            APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_INVALID
        )

    def _write_external_checkpoint(
        self,
        connection,
    ) -> None:
        path = self._external_checkpoint_path(
            connection
        )

        if path is None:
            return

        (
            sequence_id,
            commitment_sha256,
        ) = self._current_tail_checkpoint(
            connection
        )

        expected = self._external_checkpoint_text(
            sequence_id=sequence_id,
            commitment_sha256=commitment_sha256,
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = path.with_name(
            path.name
            + ".tmp-"
            + str(os.getpid())
        )

        try:
            if temporary.exists():
                temporary.unlink()

            with temporary.open(
                "x",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(expected)
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            os.replace(
                temporary,
                path,
            )

            if (
                path.read_text(
                    encoding="utf-8"
                )
                != expected
            ):
                raise ValueError(
                    APPEND_ONLY_TAIL_GUARD_EXTERNAL_CHECKPOINT_INVALID
                )

        finally:
            if temporary.exists():
                temporary.unlink()

    def _recover_external_checkpoint_if_valid_extension(
        self,
        connection,
    ) -> None:
        relation = (
            self._external_checkpoint_relation(
                connection
            )
        )

        self._raise_for_external_checkpoint_relation(
            relation,
            allow_behind=True,
        )

        if relation == "BEHIND":
            self._write_external_checkpoint(
                connection
            )

    def require_current_external_checkpoint(
        self,
        connection,
    ) -> None:
        relation = (
            self._external_checkpoint_relation(
                connection
            )
        )

        self._raise_for_external_checkpoint_relation(
            relation,
            allow_behind=False,
        )

    def synchronize_external_checkpoint(
        self,
        connection,
    ) -> None:
        if (
            self._external_checkpoint_path(
                connection
            )
            is None
        ):
            return

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            relation = (
                self._external_checkpoint_relation(
                    connection
                )
            )

            self._raise_for_external_checkpoint_relation(
                relation,
                allow_behind=True,
            )

            if relation == "BEHIND":
                self._write_external_checkpoint(
                    connection
                )

            connection.commit()

        except Exception:
            connection.rollback()
            self._baseline_valid = False
            raise

    def _current_freshness_state(
        self,
        connection,
    ) -> FreshnessState:
        sequence_id, commitment_sha256 = (
            self._current_tail_checkpoint(
                connection
            )
        )

        return FreshnessState(
            namespace=self.freshness_namespace,
            sequence_id=sequence_id,
            commitment_sha256=commitment_sha256,
        )

    def _freshness_relation(
        self,
        connection,
        state: FreshnessState,
    ) -> str:
        current = self._current_freshness_state(
            connection
        )

        if (
            state.namespace
            != self.freshness_namespace
        ):
            return "DIVERGENCE"

        if (
            state.sequence_id
            > current.sequence_id
        ):
            return "ROLLBACK"

        if (
            state.sequence_id
            == current.sequence_id
        ):
            if (
                state.commitment_sha256
                == current.commitment_sha256
            ):
                return "MATCH"

            return "DIVERGENCE"

        if state.sequence_id == 0:
            if (
                state.commitment_sha256
                is None
            ):
                return "BEHIND"

            return "DIVERGENCE"

        row = connection.execute(
            f"SELECT commitment_sha256 "
            f"FROM {self.table_name} "
            f"WHERE sequence_id = ?",
            (
                state.sequence_id,
            ),
        ).fetchone()

        if row is None:
            return "DIVERGENCE"

        if (
            str(row[0])
            != state.commitment_sha256
        ):
            return "DIVERGENCE"

        return "BEHIND"

    def _raise_for_freshness_relation(
        self,
        relation: str,
        *,
        allow_behind: bool,
    ) -> None:
        if relation == "MATCH":
            return

        if (
            relation == "BEHIND"
            and allow_behind
        ):
            return

        self._baseline_valid = False

        if relation == "ROLLBACK":
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_ROLLBACK"
            )

        if relation == "DIVERGENCE":
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_DIVERGENCE"
            )

        if relation == "BEHIND":
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_NOT_CURRENT"
            )

        raise ValueError(
            "APPEND_ONLY_TAIL_GUARD_"
            "FRESHNESS_ROOT_INVALID"
        )

    def initialize_or_reconcile_freshness_root(
        self,
        connection,
    ) -> None:
        root = self.freshness_root

        if root is None:
            return

        namespace = self.freshness_namespace

        current = self._current_freshness_state(
            connection
        )

        observed = root.read(
            namespace
        )

        pending = root.read_pending(
            namespace
        )

        if observed is None:
            if pending is not None:
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_RESERVATION_INVALID"
                )

            if (
                current.sequence_id != 0
                or self._state_preexisted
            ):
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_ROOT_STATE_REQUIRED"
                )

            if root.initialize(
                namespace=namespace,
                state=current,
            ):
                return

            latest = root.read(
                namespace
            )

            latest_pending = root.read_pending(
                namespace
            )

            if (
                latest == current
                and latest_pending is None
            ):
                return

            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_CAS_CONFLICT"
            )

        if pending is not None:
            if pending.namespace != namespace:
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_RESERVATION_INVALID"
                )

            if current == pending.intended:
                if observed not in {
                    pending.expected,
                    pending.intended,
                }:
                    self._baseline_valid = False
                    raise ValueError(
                        "APPEND_ONLY_TAIL_GUARD_"
                        "FRESHNESS_RESERVATION_DIVERGENCE"
                    )

                if not root.finalize(
                    namespace=namespace,
                    transaction_id=(
                        pending.transaction_id
                    ),
                    intended=pending.intended,
                ):
                    self._baseline_valid = False
                    raise ValueError(
                        "APPEND_ONLY_TAIL_GUARD_"
                        "FRESHNESS_RESERVATION_FINALIZE_FAILED"
                    )

                latest = root.read(namespace)
                latest_pending = (
                    root.read_pending(
                        namespace
                    )
                )

                if (
                    latest != current
                    or latest_pending is not None
                ):
                    self._baseline_valid = False
                    raise ValueError(
                        "APPEND_ONLY_TAIL_GUARD_"
                        "FRESHNESS_RESERVATION_FINALIZE_FAILED"
                    )

                return

            if (
                current == pending.expected
                and observed
                == pending.expected
            ):
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_RESERVATION_PENDING_REVIEW"
                )

            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_DIVERGENCE"
            )

        relation = self._freshness_relation(
            connection,
            observed,
        )

        if relation == "MATCH":
            return

        if relation == "BEHIND":
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_UNPREPARED_EXTENSION"
            )

        self._raise_for_freshness_relation(
            relation,
            allow_behind=False,
        )

    def require_current_freshness_root(
        self,
        connection,
    ) -> None:
        root = self.freshness_root

        if root is None:
            return

        namespace = self.freshness_namespace

        observed = root.read(
            namespace
        )

        if observed is None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_STATE_REQUIRED"
            )

        if root.read_pending(
            namespace
        ) is not None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_PENDING_REVIEW"
            )

        relation = self._freshness_relation(
            connection,
            observed,
        )

        self._raise_for_freshness_relation(
            relation,
            allow_behind=False,
        )

    def synchronize_freshness_root(
        self,
        connection,
    ) -> None:
        if self.freshness_root is None:
            return

        self.initialize_or_reconcile_freshness_root(
            connection
        )

    def prepare_freshness_transition(
        self,
        connection,
    ) -> FreshnessReservation | None:
        root = self.freshness_root

        if root is None:
            return None

        namespace = self.freshness_namespace

        expected = root.read(
            namespace
        )

        if expected is None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_ROOT_STATE_REQUIRED"
            )

        if root.read_pending(
            namespace
        ) is not None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_PENDING_REVIEW"
            )

        relation = self._freshness_relation(
            connection,
            expected,
        )

        if relation != "BEHIND":
            if relation == "MATCH":
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_RESERVATION_NO_TRANSITION"
                )

            self._raise_for_freshness_relation(
                relation,
                allow_behind=False,
            )

        intended = (
            self._current_freshness_state(
                connection
            )
        )

        transaction_id = uuid4().hex

        if not root.prepare(
            namespace=namespace,
            expected=expected,
            intended=intended,
            transaction_id=transaction_id,
        ):
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_CONFLICT"
            )

        return FreshnessReservation(
            namespace=namespace,
            transaction_id=transaction_id,
            expected=expected,
            intended=intended,
        )

    def finalize_freshness_transition(
        self,
        reservation: FreshnessReservation | None,
    ) -> None:
        root = self.freshness_root

        if root is None:
            if reservation is not None:
                self._baseline_valid = False
                raise ValueError(
                    "APPEND_ONLY_TAIL_GUARD_"
                    "FRESHNESS_RESERVATION_INVALID"
                )
            return

        if reservation is None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_REQUIRED"
            )

        namespace = self.freshness_namespace

        if reservation.namespace != namespace:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_INVALID"
            )

        if not root.finalize(
            namespace=namespace,
            transaction_id=(
                reservation.transaction_id
            ),
            intended=reservation.intended,
        ):
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_FINALIZE_FAILED"
            )

        if (
            root.read(namespace)
            != reservation.intended
            or root.read_pending(
                namespace
            ) is not None
        ):
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_FINALIZE_FAILED"
            )

    def abort_freshness_transition(
        self,
        reservation: FreshnessReservation | None,
    ) -> None:
        if reservation is None:
            return

        root = self.freshness_root

        if root is None:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_INVALID"
            )

        namespace = self.freshness_namespace

        if reservation.namespace != namespace:
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_INVALID"
            )

        if not root.abort(
            namespace=namespace,
            transaction_id=(
                reservation.transaction_id
            ),
            expected=reservation.expected,
        ):
            self._baseline_valid = False
            raise ValueError(
                "APPEND_ONLY_TAIL_GUARD_"
                "FRESHNESS_RESERVATION_ABORT_FAILED"
            )

    def resolve_failed_freshness_transition(
        self,
        connection,
        reservation: FreshnessReservation | None,
    ) -> None:
        if connection.in_transaction:
            connection.rollback()

        if reservation is None:
            return

        current = self._current_freshness_state(
            connection
        )

        if current == reservation.expected:
            self.abort_freshness_transition(
                reservation
            )
            return

        if current == reservation.intended:
            # Commit may have become durable before the exception
            # was observable. Preserve PENDING for restart recovery.
            return

        self._baseline_valid = False
        raise ValueError(
            "APPEND_ONLY_TAIL_GUARD_"
            "FRESHNESS_TRANSACTION_OUTCOME_DIVERGENCE"
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

        checkpoint_relation = (
            self._external_checkpoint_relation(
                connection
            )
        )
        self._raise_for_external_checkpoint_relation(
            checkpoint_relation,
            allow_behind=True,
        )

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
            if anchor_status == "MISSING":
                self._baseline_valid = False
                raise ValueError(
                    APPEND_ONLY_TAIL_GUARD_EXTERNAL_ANCHOR_REQUIRED
                )

            report = self._audit_core(connection, rows)
            self._baseline_valid = report.ok

            if not report.ok:
                return

            self._recover_external_checkpoint_if_valid_extension(
                connection
            )

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
            self._write_external_checkpoint(connection)
            self._baseline_valid = True
            return

        connection.execute(
            f"INSERT INTO {self.state_table_name} "
            "(ledger_name, guard_table_name, initialization_marker_sha256) "
            "VALUES (?, ?, ?)",
            (self.ledger_name, self.table_name, self._state_marker_sha256()),
        )
        self._write_external_anchor(connection)
        self._write_external_checkpoint(connection)
        self._baseline_valid = True

    def audit(self, connection, *, records: Iterable[tuple[str, str]]) -> AppendOnlyTailGuardIntegrityReport:
        self.ensure_schema(connection)
        protected = tuple((str(record_id), str(payload_sha)) for record_id, payload_sha in records)
        report = self._audit_core(connection, protected)
        self._baseline_valid = report.ok
        return report
