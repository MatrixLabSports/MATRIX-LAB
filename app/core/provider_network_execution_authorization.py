from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from app.core.provider_dns_egress_guard import (
    resolve_and_validate_provider_egress,
)
from app.core.provider_execution_authorization import (
    verify_provider_execution_authorization,
)
from app.core.provider_security_authorization import (
    evaluate_authoritative_provider_security,
)


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


@dataclass(frozen=True)
class ProviderNetworkPermit:
    permit_id: str
    run_id: str
    sport: str
    provider_key: str
    mode: str
    request_nonce: str
    method: str
    endpoint_manifest_id: str
    endpoint_authorization_fingerprint: str
    dns_resolution_fingerprint: str
    resolved_ips: tuple[str, ...]
    execution_authorization_fingerprint: str
    security_decision_fingerprint: str
    security_evidence_id: str
    issued_at: datetime



def _network_permit_id_from_payload(
    payload: Mapping[str, Any],
) -> str:
    required = (
        "run_id",
        "sport",
        "provider_key",
        "mode",
        "request_nonce",
        "method",
        "endpoint_manifest_id",
        "endpoint_authorization_fingerprint",
        "dns_resolution_fingerprint",
        "resolved_ips",
        "execution_authorization_fingerprint",
        "security_decision_fingerprint",
        "security_evidence_id",
        "issued_at",
    )

    for key in required:
        if key not in payload:
            raise ValueError(
                f"NETWORK_PERMIT_MISSING_FIELD:{key}"
            )

    resolved_ips = payload["resolved_ips"]

    if (
        not isinstance(resolved_ips, list)
        or not resolved_ips
        or any(
            not isinstance(item, str) or not item
            for item in resolved_ips
        )
    ):
        raise ValueError(
            "INVALID_NETWORK_PERMIT_RESOLVED_IPS"
        )

    if payload.get("one_use") is not True:
        raise ValueError(
            "NETWORK_PERMIT_ONE_USE_REQUIRED"
        )

    if payload.get("automatic_provider_switch") is not False:
        raise ValueError(
            "AUTOMATIC_PROVIDER_SWITCH_MUST_REMAIN_FALSE"
        )

    base = {
        "schema": "matrix.provider-network-permit-id/1",
        "run_id": payload["run_id"],
        "sport": payload["sport"],
        "provider_key": payload["provider_key"],
        "mode": payload["mode"],
        "request_nonce": payload["request_nonce"],
        "method": payload["method"],
        "endpoint_manifest_id": payload["endpoint_manifest_id"],
        "endpoint_authorization_fingerprint": payload[
            "endpoint_authorization_fingerprint"
        ],
        "dns_resolution_fingerprint": payload[
            "dns_resolution_fingerprint"
        ],
        "resolved_ips": list(resolved_ips),
        "execution_authorization_fingerprint": payload[
            "execution_authorization_fingerprint"
        ],
        "security_decision_fingerprint": payload[
            "security_decision_fingerprint"
        ],
        "security_evidence_id": payload[
            "security_evidence_id"
        ],
        "issued_at": payload["issued_at"],
        "one_use": True,
    }

    return _sha(base)


def _verify_network_permit_row(
    *,
    expected_permit_id: str,
    payload_json: str,
    payload_sha256: str,
) -> Mapping[str, Any]:
    actual_sha = sha256(
        payload_json.encode("utf-8")
    ).hexdigest()

    if actual_sha != payload_sha256:
        raise ValueError(
            "NETWORK_PERMIT_INTEGRITY_FAILURE"
        )

    try:
        payload = json.loads(payload_json)
    except Exception as error:
        raise ValueError(
            "NETWORK_PERMIT_INVALID_JSON"
        ) from error

    if (
        payload.get("schema")
        != "matrix.provider-network-permit/1"
    ):
        raise ValueError(
            "NETWORK_PERMIT_SCHEMA_MISMATCH"
        )

    if payload.get("permit_id") != expected_permit_id:
        raise ValueError(
            "NETWORK_PERMIT_ID_MISMATCH"
        )

    if (
        _network_permit_id_from_payload(payload)
        != expected_permit_id
    ):
        raise ValueError(
            "NETWORK_PERMIT_REDERIVATION_FAILURE"
        )

    return payload


class SQLiteProviderNetworkPermitStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS network_permit (
                    permit_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    request_nonce TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    consumed_at TEXT,
                    UNIQUE(run_id, request_nonce)
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

    def issue(self, permit: ProviderNetworkPermit) -> str:
        payload = {
            "schema": "matrix.provider-network-permit/1",
            **permit.__dict__,
            "issued_at": permit.issued_at.isoformat(),
            "one_use": True,
            "automatic_provider_switch": False,
        }
        payload_json = _json(payload)
        payload_sha = sha256(payload_json.encode()).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT 1 FROM network_permit
                WHERE run_id = ? AND request_nonce = ?
                """,
                (permit.run_id, permit.request_nonce),
            ).fetchone()
            if row is not None:
                connection.execute("ROLLBACK")
                raise ValueError("NETWORK_REQUEST_NONCE_ALREADY_USED")

            connection.execute(
                """
                INSERT INTO network_permit
                (permit_id, run_id, request_nonce, payload_json, payload_sha256, consumed_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    permit.permit_id,
                    permit.run_id,
                    permit.request_nonce,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")
        return permit.permit_id

    def consume(
        self,
        *,
        permit_id: str,
        consumed_at: datetime,
    ) -> Mapping[str, Any]:
        consumed_at = _aware(consumed_at)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256, consumed_at
                FROM network_permit
                WHERE permit_id = ?
                """,
                (permit_id,),
            ).fetchone()

            if row is None:
                connection.execute("ROLLBACK")
                raise ValueError("UNKNOWN_NETWORK_PERMIT")

            payload_json, payload_sha, already = row
            if already is not None:
                connection.execute("ROLLBACK")
                raise ValueError("NETWORK_PERMIT_ALREADY_CONSUMED")

            try:
                payload = _verify_network_permit_row(
                    expected_permit_id=permit_id,
                    payload_json=payload_json,
                    payload_sha256=payload_sha,
                )
            except ValueError:
                connection.execute("ROLLBACK")
                raise

            connection.execute(
                """
                UPDATE network_permit
                SET consumed_at = ?
                WHERE permit_id = ? AND consumed_at IS NULL
                """,
                (consumed_at.isoformat(), permit_id),
            )
            connection.execute("COMMIT")

        return payload

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT permit_id, run_id, request_nonce, "
                "payload_json, payload_sha256, consumed_at "
                "FROM network_permit ORDER BY permit_id"
            ).fetchall()

        seen_run_nonce: set[
            tuple[str, str]
        ] = set()

        for (
            permit_id,
            run_id,
            request_nonce,
            payload_json,
            payload_sha,
            consumed_at,
        ) in rows:
            try:
                payload = _verify_network_permit_row(
                    expected_permit_id=str(permit_id),
                    payload_json=str(payload_json),
                    payload_sha256=str(payload_sha),
                )
            except ValueError:
                return False

            if (
                payload.get("run_id") != run_id
                or payload.get("request_nonce")
                != request_nonce
            ):
                return False

            key = (
                str(run_id),
                str(request_nonce),
            )

            if key in seen_run_nonce:
                return False

            seen_run_nonce.add(key)

            if consumed_at is not None:
                try:
                    consumed = datetime.fromisoformat(
                        str(consumed_at)
                    )
                except Exception:
                    return False

                if consumed.tzinfo is None:
                    return False

        return True


class ProviderNetworkAuthority:
    def __init__(
        self,
        *,
        run_id: str,
        sport: str,
        provider_key: str,
        mode: str,
        queue_manifest: Mapping[str, Any],
        scheduling_authorization_fingerprint: str,
        scheduling_evidence_ledger,
        health_evidence_ledger,
        preflight_decision: object,
        preflight_evidence_store,
        security_evidence_store,
        endpoint_registry,
        secret_reference: object,
        secret_reference_fingerprint: str,
        secret_reference_registry,
        network_permit_store: SQLiteProviderNetworkPermitStore,
        run_mode_evidence_store,
        clock: Callable[[], datetime],
        resolver=None,
    ) -> None:
        self.run_id = run_id
        self.sport = sport
        self.provider_key = provider_key
        self.mode = mode
        self.queue_manifest = queue_manifest
        self.scheduling_authorization_fingerprint = scheduling_authorization_fingerprint
        self.scheduling_evidence_ledger = scheduling_evidence_ledger
        self.health_evidence_ledger = health_evidence_ledger
        self.preflight_decision = preflight_decision
        self.preflight_evidence_store = preflight_evidence_store
        self.security_evidence_store = security_evidence_store
        self.endpoint_registry = endpoint_registry
        self.secret_reference = secret_reference
        self.secret_reference_fingerprint = secret_reference_fingerprint
        self.secret_reference_registry = secret_reference_registry
        self.network_permit_store = network_permit_store
        self.run_mode_evidence_store = run_mode_evidence_store
        self.clock = clock
        self.resolver = resolver

    def authorize(
        self,
        *,
        request_nonce: str,
        method: str,
        endpoint_url: str,
        query_keys: Sequence[str],
    ) -> ProviderNetworkPermit:
        now = _aware(self.clock())

        if self.mode not in {"PRODUCTION", "BOOTSTRAP_PROBE"}:
            raise ValueError("UNSUPPORTED_PROVIDER_MODE")

        for name, expected in (
            ("status", "EXECUTE"),
            ("executable", True),
            ("run_id", self.run_id),
            ("sport", self.sport),
            ("provider_key", self.provider_key),
            ("mode", self.mode),
        ):
            if getattr(self.preflight_decision, name, None) != expected:
                raise ValueError("PREFLIGHT_BINDING_OR_STATUS_MISMATCH")

        execution = verify_provider_execution_authorization(
            queue_manifest=self.queue_manifest,
            authorization_fingerprint=self.scheduling_authorization_fingerprint,
            scheduling_evidence_ledger=self.scheduling_evidence_ledger,
            health_evidence_ledger=self.health_evidence_ledger,
            expected_sport=self.sport,
        )

        endpoint = self.endpoint_registry.authorize_request(
            provider_key=self.provider_key,
            sport=self.sport,
            method=method,
            endpoint_url=endpoint_url,
            query_keys=query_keys,
            secret_reference_fingerprint=self.secret_reference_fingerprint,
            as_of=now,
        )

        if endpoint.status != "AUTHORIZED" or endpoint.executable is not True:
            raise ValueError("ENDPOINT_NOT_AUTHORIZED")
        if endpoint.manifest_id is None:
            raise ValueError("ENDPOINT_MANIFEST_MISSING")

        security = evaluate_authoritative_provider_security(
            run_id=self.run_id,
            sport=self.sport,
            provider_key=self.provider_key,
            mode=self.mode,
            preflight_decision=self.preflight_decision,
            preflight_evidence_store=self.preflight_evidence_store,
            endpoint_url=endpoint_url,
            secret_reference=self.secret_reference,
            secret_reference_registry=self.secret_reference_registry,
        )

        if (
            getattr(security, "status", None) != "EXECUTE"
            or getattr(security, "executable", None) is not True
        ):
            raise ValueError("SECURITY_NOT_EXECUTABLE")

        security_evidence_id = self.security_evidence_store.record(security)

        preflight_fp = str(getattr(self.preflight_decision, "decision_fingerprint", ""))
        if len(preflight_fp) != 64:
            raise ValueError("PREFLIGHT_DECISION_FINGERPRINT_REQUIRED")
        self.run_mode_evidence_store.record(
            run_id=self.run_id,
            sport=self.sport,
            provider_key=self.provider_key,
            mode=self.mode,
            preflight_decision_fingerprint=preflight_fp,
            authorized_at=now,
        )

        parsed = urlsplit(endpoint_url)
        dns = resolve_and_validate_provider_egress(
            host=parsed.hostname or "",
            port=parsed.port or 443,
            resolver=self.resolver,
        )
        if dns.status != "AUTHORIZED" or dns.executable is not True:
            raise ValueError("EGRESS_NOT_AUTHORIZED")

        execution_fp = _sha(execution.payload())
        security_fp = str(getattr(security, "decision_fingerprint", ""))

        base = {
            "schema": "matrix.provider-network-permit-id/1",
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "request_nonce": request_nonce,
            "method": method.upper(),
            "endpoint_manifest_id": endpoint.manifest_id,
            "endpoint_authorization_fingerprint": endpoint.decision_fingerprint,
            "dns_resolution_fingerprint": dns.resolution_fingerprint,
            "resolved_ips": list(dns.resolved_ips),
            "execution_authorization_fingerprint": execution_fp,
            "security_decision_fingerprint": security_fp,
            "security_evidence_id": security_evidence_id,
            "issued_at": now.isoformat(),
            "one_use": True,
        }

        permit = ProviderNetworkPermit(
            permit_id=_sha(base),
            run_id=self.run_id,
            sport=self.sport,
            provider_key=self.provider_key,
            mode=self.mode,
            request_nonce=request_nonce,
            method=method.upper(),
            endpoint_manifest_id=endpoint.manifest_id,
            endpoint_authorization_fingerprint=endpoint.decision_fingerprint,
            dns_resolution_fingerprint=dns.resolution_fingerprint,
            resolved_ips=tuple(dns.resolved_ips),
            execution_authorization_fingerprint=execution_fp,
            security_decision_fingerprint=security_fp,
            security_evidence_id=security_evidence_id,
            issued_at=now,
        )

        self.network_permit_store.issue(permit)
        return permit
