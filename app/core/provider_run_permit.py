from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class ProviderRunPermit:
    permit_id: str
    run_id: str
    sport: str
    provider_key: str
    mode: str
    queue_fingerprint: str
    scheduling_evidence_fingerprint: str
    rights_manifest_fingerprint: str
    bootstrap_policy_fingerprint: str | None
    max_items: int
    max_requests: int
    permit_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-run-permit/1",
            "permit_id": self.permit_id,
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "queue_fingerprint": self.queue_fingerprint,
            "scheduling_evidence_fingerprint": (
                self.scheduling_evidence_fingerprint
            ),
            "rights_manifest_fingerprint": (
                self.rights_manifest_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                self.bootstrap_policy_fingerprint
            ),
            "max_items": self.max_items,
            "max_requests": self.max_requests,
            "one_use": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "permit_fingerprint": self.permit_fingerprint,
        }


class SQLiteProviderRunPermitStore:
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
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_run_permits (
                    permit_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    queue_fingerprint TEXT NOT NULL,
                    permit_fingerprint TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    consumed_at TEXT,
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (mode IN ('PRODUCTION', 'BOOTSTRAP_PROBE')),
                    CHECK (state IN ('ISSUED', 'CONSUMED'))
                )
                """
            )

    @staticmethod
    def build_permit(
        *,
        run_id: str,
        sport: str,
        provider_key: str,
        mode: str,
        queue_fingerprint: str,
        scheduling_evidence_fingerprint: str,
        rights_manifest_fingerprint: str,
        bootstrap_policy_fingerprint: str | None,
        max_items: int,
        max_requests: int,
    ) -> ProviderRunPermit:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("INVALID_RUN_ID")
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")
        if not isinstance(provider_key, str) or not provider_key:
            raise ValueError("INVALID_PROVIDER_KEY")
        if mode not in {"PRODUCTION", "BOOTSTRAP_PROBE"}:
            raise ValueError("INVALID_PROVIDER_MODE")

        queue_fingerprint = _hex64(
            "QUEUE_FINGERPRINT",
            queue_fingerprint,
        )
        scheduling_evidence_fingerprint = _hex64(
            "SCHEDULING_EVIDENCE_FINGERPRINT",
            scheduling_evidence_fingerprint,
        )
        rights_manifest_fingerprint = _hex64(
            "RIGHTS_MANIFEST_FINGERPRINT",
            rights_manifest_fingerprint,
        )

        if mode == "BOOTSTRAP_PROBE":
            if bootstrap_policy_fingerprint is None:
                raise ValueError("BOOTSTRAP_POLICY_REQUIRED")
            bootstrap_policy_fingerprint = _hex64(
                "BOOTSTRAP_POLICY_FINGERPRINT",
                bootstrap_policy_fingerprint,
            )
        elif bootstrap_policy_fingerprint is not None:
            raise ValueError("BOOTSTRAP_POLICY_NOT_ALLOWED_IN_PRODUCTION")

        for name, value in {
            "MAX_ITEMS": max_items,
            "MAX_REQUESTS": max_requests,
        }.items():
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise ValueError(f"INVALID_{name}")

        base = {
            "schema": "matrix.provider-run-permit/1",
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "queue_fingerprint": queue_fingerprint,
            "scheduling_evidence_fingerprint": (
                scheduling_evidence_fingerprint
            ),
            "rights_manifest_fingerprint": (
                rights_manifest_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                bootstrap_policy_fingerprint
            ),
            "max_items": max_items,
            "max_requests": max_requests,
            "one_use": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
        permit_fingerprint = _sha(base)
        permit_id = _sha(
            {
                "schema": "matrix.provider-run-permit-id/1",
                "permit_fingerprint": permit_fingerprint,
            }
        )
        return ProviderRunPermit(
            permit_id=permit_id,
            run_id=run_id,
            sport=sport,
            provider_key=provider_key,
            mode=mode,
            queue_fingerprint=queue_fingerprint,
            scheduling_evidence_fingerprint=(
                scheduling_evidence_fingerprint
            ),
            rights_manifest_fingerprint=(
                rights_manifest_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                bootstrap_policy_fingerprint
            ),
            max_items=max_items,
            max_requests=max_requests,
            permit_fingerprint=permit_fingerprint,
        )

    def issue(
        self,
        permit: ProviderRunPermit,
    ) -> ProviderRunPermit:
        expected = self.build_permit(
            run_id=permit.run_id,
            sport=permit.sport,
            provider_key=permit.provider_key,
            mode=permit.mode,
            queue_fingerprint=permit.queue_fingerprint,
            scheduling_evidence_fingerprint=(
                permit.scheduling_evidence_fingerprint
            ),
            rights_manifest_fingerprint=(
                permit.rights_manifest_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                permit.bootstrap_policy_fingerprint
            ),
            max_items=permit.max_items,
            max_requests=permit.max_requests,
        )
        if expected != permit:
            raise ValueError("PROVIDER_RUN_PERMIT_DERIVATION_MISMATCH")

        payload_json = _canonical_json(permit.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT permit_id, payload_sha256, state
                FROM provider_run_permits
                WHERE run_id = ?
                """,
                (permit.run_id,),
            ).fetchone()
            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == permit.permit_id
                    and str(existing[1]) == payload_sha
                    and str(existing[2]) == "ISSUED"
                ):
                    return permit
                raise ValueError("RUN_ALREADY_HAS_PERMIT")

            connection.execute(
                """
                INSERT INTO provider_run_permits (
                    permit_id,
                    run_id,
                    sport,
                    provider_key,
                    mode,
                    queue_fingerprint,
                    permit_fingerprint,
                    state,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ISSUED', ?, ?)
                """,
                (
                    permit.permit_id,
                    permit.run_id,
                    permit.sport,
                    permit.provider_key,
                    permit.mode,
                    permit.queue_fingerprint,
                    permit.permit_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return permit

    def consume(
        self,
        *,
        permit_id: str,
        run_id: str,
        sport: str,
        provider_key: str,
        mode: str,
        queue_fingerprint: str,
    ) -> Mapping[str, Any]:
        queue_fingerprint = _hex64(
            "QUEUE_FINGERPRINT",
            queue_fingerprint,
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    state,
                    payload_json,
                    payload_sha256
                FROM provider_run_permits
                WHERE permit_id = ?
                """,
                (permit_id,),
            ).fetchone()

            if row is None:
                connection.execute("ROLLBACK")
                raise ValueError("UNKNOWN_PROVIDER_RUN_PERMIT")

            state, payload_json, stored_sha = row
            payload = json.loads(payload_json)
            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                connection.execute("ROLLBACK")
                raise ValueError("PROVIDER_RUN_PERMIT_INTEGRITY_VIOLATION")

            if state != "ISSUED":
                connection.execute("ROLLBACK")
                raise ValueError("PROVIDER_RUN_PERMIT_ALREADY_CONSUMED")

            expected = {
                "run_id": run_id,
                "sport": sport,
                "provider_key": provider_key,
                "mode": mode,
                "queue_fingerprint": queue_fingerprint,
            }
            for key, value in expected.items():
                if payload.get(key) != value:
                    connection.execute("ROLLBACK")
                    raise ValueError(
                        f"PROVIDER_RUN_PERMIT_BINDING_MISMATCH:{key}"
                    )

            connection.execute(
                """
                UPDATE provider_run_permits
                SET
                    state = 'CONSUMED',
                    consumed_at = strftime(
                        '%Y-%m-%dT%H:%M:%fZ',
                        'now'
                    )
                WHERE permit_id = ? AND state = 'ISSUED'
                """,
                (permit_id,),
            )
            if connection.total_changes != 1:
                connection.execute("ROLLBACK")
                raise ValueError("PROVIDER_RUN_PERMIT_CONSUME_RACE")

            connection.execute("COMMIT")
            return payload
