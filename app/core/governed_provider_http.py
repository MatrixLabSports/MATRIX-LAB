from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import monotonic
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("NAIVE_DATETIME")
    return value.astimezone(timezone.utc)


class MatrixPinnedHttpsTransport(ABC):
    # Security contract only. No concrete real-network implementation is
    # shipped in this tranche. Future implementation must pin the connection
    # to an authorized resolved IP while preserving TLS/SNI validation.
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True

    @abstractmethod
    def get_pinned(
        self,
        *,
        url: str,
        original_host: str,
        resolved_ips: tuple[str, ...],
        allow_redirects: bool,
        verify: bool,
        **kwargs: Any,
    ):
        raise NotImplementedError


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
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
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
        if event_type not in {"NETWORK_CALL_STARTED", "NETWORK_CALL_COMPLETED", "NETWORK_CALL_FAILED"}:
            raise ValueError("INVALID_NETWORK_EVENT_TYPE")

        payload = {
            "schema": "matrix.provider-network-call-event/2",
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
            "redirect_target_persisted": False,
            "proxy_configuration_persisted": False,
        }
        event_id = _sha({"schema": "matrix.provider-network-call-event-id/2", "payload": payload})
        payload_json = _json(payload)
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO network_call_event (event_id, permit_id, payload_json, payload_sha256) VALUES (?, ?, ?, ?)",
                (event_id, permit_id, payload_json, payload_sha),
            )
        return event_id

    def audit_integrity(
        self,
    ) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, permit_id, payload_json, payload_sha256 "
                "FROM network_call_event ORDER BY permit_id, event_id"
            ).fetchall()

        by_permit: dict[
            str,
            list[Mapping[str, Any]],
        ] = {}

        for (
            event_id,
            permit_id,
            payload_json,
            payload_sha,
        ) in rows:
            if (
                sha256(
                    payload_json.encode("utf-8")
                ).hexdigest()
                != payload_sha
            ):
                return False

            try:
                payload = json.loads(payload_json)
            except Exception:
                return False

            expected = _sha(
                {
                    "schema": (
                        "matrix.provider-network-call-event-id/2"
                    ),
                    "payload": payload,
                }
            )

            if expected != event_id:
                return False

            if payload.get("permit_id") != permit_id:
                return False

            for key in (
                "raw_url_persisted",
                "query_values_persisted",
                "headers_persisted",
                "raw_payload_persisted",
                "secret_material_persisted",
                "redirect_target_persisted",
                "proxy_configuration_persisted",
            ):
                if payload.get(key) is not False:
                    return False

            event_type = payload.get("event_type")

            if event_type not in {
                "NETWORK_CALL_STARTED",
                "NETWORK_CALL_COMPLETED",
                "NETWORK_CALL_FAILED",
            }:
                return False

            try:
                event_at = datetime.fromisoformat(
                    payload["event_at"]
                )
            except Exception:
                return False

            if event_at.tzinfo is None:
                return False

            by_permit.setdefault(
                str(permit_id),
                [],
            ).append(payload)

        for events in by_permit.values():
            started = [
                event
                for event in events
                if event["event_type"]
                == "NETWORK_CALL_STARTED"
            ]

            terminal = [
                event
                for event in events
                if event["event_type"]
                in {
                    "NETWORK_CALL_COMPLETED",
                    "NETWORK_CALL_FAILED",
                }
            ]

            if len(started) != 1:
                return False

            if len(terminal) != 1:
                return False

            start_at = datetime.fromisoformat(
                started[0]["event_at"]
            )

            terminal_at = datetime.fromisoformat(
                terminal[0]["event_at"]
            )

            if terminal_at < start_at:
                return False

            terminal_type = terminal[0]["event_type"]

            if (
                terminal_type
                == "NETWORK_CALL_COMPLETED"
                and terminal[0].get(
                    "exception_class"
                )
                is not None
            ):
                return False

            if (
                terminal_type
                == "NETWORK_CALL_FAILED"
                and not terminal[0].get(
                    "exception_class"
                )
            ):
                return False

        return True



class GovernedProviderHttpSession:
    def __init__(
        self,
        *,
        authority,
        network_permit_store,
        call_evidence_store: SQLiteProviderNetworkCallEvidenceStore,
        pinned_transport: MatrixPinnedHttpsTransport,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(pinned_transport, MatrixPinnedHttpsTransport):
            raise ValueError("PINNED_HTTPS_TRANSPORT_REQUIRED")
        self.authority = authority
        self.network_permit_store = network_permit_store
        self.call_evidence_store = call_evidence_store
        self.pinned_transport = pinned_transport
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
        result: list[str] = []
        for item in list(params):
            if not isinstance(item, tuple) or len(item) < 2:
                raise ValueError("UNSUPPORTED_QUERY_PARAMS")
            result.append(str(item[0]).lower())
        return tuple(sorted(set(result)))

    @staticmethod
    def _secure_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        if "allow_redirects" in kwargs and kwargs["allow_redirects"] is not False:
            raise ValueError("HTTP_REDIRECTS_FORBIDDEN")
        if "verify" in kwargs and kwargs["verify"] is not True:
            raise ValueError("TLS_VERIFICATION_MUST_REMAIN_ENABLED")
        if "proxies" in kwargs or "proxy" in kwargs:
            raise ValueError("EXPLICIT_PROXY_FORBIDDEN")

        clean = dict(kwargs)
        clean.pop("allow_redirects", None)
        clean.pop("verify", None)
        clean["allow_redirects"] = False
        clean["verify"] = True
        return clean

    def get(self, url: str, **kwargs: Any):
        kwargs = self._secure_kwargs(dict(kwargs))
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("GOVERNED_HTTPS_URL_REQUIRED")

        permit = self.authority.authorize(
            request_nonce=self._nonce(),
            method="GET",
            endpoint_url=url,
            query_keys=self._query_keys(kwargs.get("params")),
        )
        resolved_ips = tuple(getattr(permit, "resolved_ips", ()))
        if not resolved_ips:
            raise ValueError("PINNED_RESOLUTION_REQUIRED")

        now = _aware(self.clock())
        self.network_permit_store.consume(permit_id=permit.permit_id, consumed_at=now)

        common = {
            "permit_id": permit.permit_id,
            "provider_key": permit.provider_key,
            "run_id": permit.run_id,
            "method": permit.method,
            "endpoint_manifest_id": permit.endpoint_manifest_id,
        }
        self.call_evidence_store.record(**common, event_type="NETWORK_CALL_STARTED", event_at=now)
        started = monotonic()

        try:
            response = self.pinned_transport.get_pinned(
                url=url,
                original_host=parsed.hostname,
                resolved_ips=resolved_ips,
                **kwargs,
            )
        except Exception as error:
            elapsed_ms = int(max(0.0, (monotonic() - started) * 1000.0))
            self.call_evidence_store.record(
                **common,
                event_type="NETWORK_CALL_FAILED",
                event_at=_aware(self.clock()),
                elapsed_ms=elapsed_ms,
                exception_class=type(error).__name__,
            )
            raise

        elapsed_ms = int(max(0.0, (monotonic() - started) * 1000.0))
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
