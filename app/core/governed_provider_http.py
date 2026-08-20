from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import monotonic
from typing import Any, Callable, Mapping


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("NAIVE_DATETIME")
    return value.astimezone(timezone.utc)


class SQLiteProviderNetworkCallEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS network_call_event (
                    event_id TEXT PRIMARY KEY,
                    permit_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def record(
        self,
        *,
        permit_id: str,
        event_type: str,
        event_at: datetime,
        provider_key: str,
        run_id: str,
        method: str,
        endpoint_manifest_id: str,
        status_code: int | None = None,
        elapsed_ms: int | None = None,
        exception_class: str | None = None,
    ) -> str:
        if event_type not in {
            "NETWORK_CALL_STARTED",
            "NETWORK_CALL_COMPLETED",
            "NETWORK_CALL_FAILED",
        }:
            raise ValueError("INVALID_NETWORK_EVENT_TYPE")

        payload = {
            "schema": "matrix.provider-network-call-event/1",
            "permit_id": permit_id,
            "event_type": event_type,
            "event_at": _aware(event_at).isoformat(),
            "provider_key": provider_key,
            "run_id": run_id,
            "method": method,
            "endpoint_manifest_id": endpoint_manifest_id,
            "status_code": status_code,
            "elapsed_ms": elapsed_ms,
            "exception_class": exception_class,
            "raw_url_persisted": False,
            "query_values_persisted": False,
            "headers_persisted": False,
            "raw_payload_persisted": False,
            "secret_material_persisted": False,
        }

        event_id = _sha(
            {"schema": "matrix.provider-network-call-event-id/1", "payload": payload}
        )
        payload_json = _json(payload)
        payload_sha = sha256(payload_json.encode()).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO network_call_event
                (event_id, permit_id, payload_json, payload_sha256)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, permit_id, payload_json, payload_sha),
            )
        return event_id

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, payload_json, payload_sha256 FROM network_call_event"
            ).fetchall()

        for event_id, payload_json, payload_sha in rows:
            if sha256(payload_json.encode()).hexdigest() != payload_sha:
                return False
            payload = json.loads(payload_json)
            expected = _sha(
                {"schema": "matrix.provider-network-call-event-id/1", "payload": payload}
            )
            if expected != event_id:
                return False
            for key in (
                "raw_url_persisted",
                "query_values_persisted",
                "headers_persisted",
                "raw_payload_persisted",
                "secret_material_persisted",
            ):
                if payload.get(key) is not False:
                    return False
        return True


class GovernedProviderHttpSession:
    def __init__(
        self,
        *,
        authority,
        network_permit_store,
        call_evidence_store: SQLiteProviderNetworkCallEvidenceStore,
        underlying_session,
        clock: Callable[[], datetime],
    ) -> None:
        self.authority = authority
        self.network_permit_store = network_permit_store
        self.call_evidence_store = call_evidence_store
        self.underlying_session = underlying_session
        self.clock = clock
        self._sequence = 0

    def _nonce(self) -> str:
        self._sequence += 1
        return f"{self.authority.run_id}:{self._sequence}"

    @staticmethod
    def _query_keys(params: object) -> tuple[str, ...]:
        if params is None:
            return ()
        if isinstance(params, Mapping):
            return tuple(sorted(str(key).lower() for key in params))

        result = []
        for item in list(params):
            if not isinstance(item, tuple) or len(item) < 2:
                raise ValueError("UNSUPPORTED_QUERY_PARAMS")
            result.append(str(item[0]).lower())
        return tuple(sorted(set(result)))

    def get(self, url: str, **kwargs: Any):
        permit = self.authority.authorize(
            request_nonce=self._nonce(),
            method="GET",
            endpoint_url=url,
            query_keys=self._query_keys(kwargs.get("params")),
        )

        now = _aware(self.clock())
        self.network_permit_store.consume(
            permit_id=permit.permit_id,
            consumed_at=now,
        )

        common = {
            "permit_id": permit.permit_id,
            "provider_key": permit.provider_key,
            "run_id": permit.run_id,
            "method": permit.method,
            "endpoint_manifest_id": permit.endpoint_manifest_id,
        }

        self.call_evidence_store.record(
            **common,
            event_type="NETWORK_CALL_STARTED",
            event_at=now,
        )

        started = monotonic()
        try:
            response = self.underlying_session.get(url, **kwargs)
        except Exception as error:
            elapsed_ms = int(max(0.0, (monotonic() - started) * 1000))
            self.call_evidence_store.record(
                **common,
                event_type="NETWORK_CALL_FAILED",
                event_at=_aware(self.clock()),
                elapsed_ms=elapsed_ms,
                exception_class=type(error).__name__,
            )
            raise

        elapsed_ms = int(max(0.0, (monotonic() - started) * 1000))
        status_code = getattr(response, "status_code", None)
        if status_code is not None and not isinstance(status_code, int):
            status_code = None

        self.call_evidence_store.record(
            **common,
            event_type="NETWORK_CALL_COMPLETED",
            event_at=_aware(self.clock()),
            elapsed_ms=elapsed_ms,
            status_code=status_code,
        )
        return response
