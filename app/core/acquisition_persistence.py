from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


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


@dataclass(frozen=True)
class StorageIntegrityReport:
    ok: bool
    raw_records: int
    checkpoints: int
    errors: tuple[str, ...]


class SQLiteAcquisitionStore:
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
                CREATE TABLE IF NOT EXISTS raw_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    queue_item_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS acquisition_checkpoints (
                    queue_item_fingerprint TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    FOREIGN KEY (evidence_id)
                        REFERENCES raw_evidence(evidence_id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT
                )
                """
            )

    def contains(self, evidence_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM raw_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

        if row is None:
            return False

        payload_json, payload_sha256 = row
        actual = _sha256_text(payload_json)
        if payload_sha256 != actual or evidence_id != actual:
            raise ValueError("RAW_EVIDENCE_INTEGRITY_VIOLATION")

        return True

    def append(
        self,
        evidence_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        queue_fingerprint = payload.get("queue_item_fingerprint")
        if (
            not isinstance(queue_fingerprint, str)
            or len(queue_fingerprint) != 64
        ):
            raise ValueError("INVALID_QUEUE_ITEM_FINGERPRINT")

        payload_json = _canonical_json(dict(payload))
        actual = _sha256_text(payload_json)

        if evidence_id != actual:
            raise ValueError("EVIDENCE_ID_PAYLOAD_MISMATCH")

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO raw_evidence (
                        evidence_id,
                        queue_item_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        queue_fingerprint,
                        payload_json,
                        actual,
                    ),
                )
                connection.execute("COMMIT")
        except sqlite3.IntegrityError as error:
            raise ValueError("RAW_APPEND_ONLY_VIOLATION") from error

    def find_evidence_for_queue_item(
        self,
        queue_item_fingerprint: str,
    ) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT evidence_id
                FROM raw_evidence
                WHERE queue_item_fingerprint = ?
                """,
                (queue_item_fingerprint,),
            ).fetchone()

        return None if row is None else str(row[0])

    def is_completed(self, queue_item_fingerprint: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM acquisition_checkpoints
                WHERE queue_item_fingerprint = ?
                """,
                (queue_item_fingerprint,),
            ).fetchone()

        return row is not None

    def mark_completed(
        self,
        queue_item_fingerprint: str,
        evidence_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            raw = connection.execute(
                """
                SELECT queue_item_fingerprint
                FROM raw_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

            if raw is None:
                connection.execute("ROLLBACK")
                raise ValueError("CHECKPOINT_WITHOUT_RAW_EVIDENCE")

            if raw[0] != queue_item_fingerprint:
                connection.execute("ROLLBACK")
                raise ValueError("CHECKPOINT_QUEUE_ITEM_MISMATCH")

            existing = connection.execute(
                """
                SELECT evidence_id
                FROM acquisition_checkpoints
                WHERE queue_item_fingerprint = ?
                """,
                (queue_item_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if existing[0] != evidence_id:
                    raise ValueError("CHECKPOINT_MUTATION_VIOLATION")
                return

            connection.execute(
                """
                INSERT INTO acquisition_checkpoints (
                    queue_item_fingerprint,
                    evidence_id
                )
                VALUES (?, ?)
                """,
                (queue_item_fingerprint, evidence_id),
            )
            connection.execute("COMMIT")

    def get_raw(self, evidence_id: str) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM raw_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def audit_integrity(self) -> StorageIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            raw_rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    queue_item_fingerprint,
                    payload_json,
                    payload_sha256
                FROM raw_evidence
                ORDER BY evidence_id
                """
            ).fetchall()

            checkpoints = connection.execute(
                """
                SELECT queue_item_fingerprint, evidence_id
                FROM acquisition_checkpoints
                ORDER BY queue_item_fingerprint
                """
            ).fetchall()

        known_evidence: dict[str, str] = {}

        for (
            evidence_id,
            queue_fingerprint,
            payload_json,
            stored_sha,
        ) in raw_rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{evidence_id}")
                continue

            canonical = _canonical_json(payload)
            actual_sha = _sha256_text(canonical)

            if stored_sha != actual_sha:
                errors.append(f"PAYLOAD_HASH_MISMATCH:{evidence_id}")

            if evidence_id != actual_sha:
                errors.append(f"EVIDENCE_ID_MISMATCH:{evidence_id}")

            if payload.get("queue_item_fingerprint") != queue_fingerprint:
                errors.append(f"QUEUE_FINGERPRINT_MISMATCH:{evidence_id}")

            known_evidence[evidence_id] = queue_fingerprint

        for queue_fingerprint, evidence_id in checkpoints:
            raw_queue = known_evidence.get(evidence_id)

            if raw_queue is None:
                errors.append(
                    f"CHECKPOINT_ORPHAN:{queue_fingerprint}"
                )
            elif raw_queue != queue_fingerprint:
                errors.append(
                    f"CHECKPOINT_QUEUE_MISMATCH:{queue_fingerprint}"
                )

        return StorageIntegrityReport(
            ok=not errors,
            raw_records=len(raw_rows),
            checkpoints=len(checkpoints),
            errors=tuple(errors),
        )
