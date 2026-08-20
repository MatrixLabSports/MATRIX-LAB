from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

from app.core.governed_provider_http import MatrixPinnedHttpsTransport


def _json(value: Any) -> str:
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
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


class ProviderNetworkBindingCollector:
    def __init__(self) -> None:
        self._active_queue_fingerprint: str | None = None
        self._evidence_ids: list[str] = []

    def begin(self, queue_item_fingerprint: str) -> None:
        if self._active_queue_fingerprint is not None:
            raise ValueError("NETWORK_BINDING_SCOPE_ALREADY_ACTIVE")
        self._active_queue_fingerprint = queue_item_fingerprint
        self._evidence_ids = []

    def record(self, evidence_id: str) -> None:
        if self._active_queue_fingerprint is None:
            raise ValueError("NETWORK_BINDING_SCOPE_REQUIRED")
        self._evidence_ids.append(evidence_id)

    def finish(self, queue_item_fingerprint: str) -> tuple[str, ...]:
        if self._active_queue_fingerprint != queue_item_fingerprint:
            raise ValueError("NETWORK_BINDING_SCOPE_MISMATCH")
        result = tuple(self._evidence_ids)
        self._active_queue_fingerprint = None
        self._evidence_ids = []
        return result


@dataclass(frozen=True)
class ProviderNetworkBindingEvidence:
    evidence_id: str
    run_id: str
    provider_key: str
    permit_id: str
    endpoint_manifest_id: str
    security_evidence_id: str
    request_contract_fingerprint: str
    outcome: str
    created_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-network-binding/1",
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "provider_key": self.provider_key,
            "permit_id": self.permit_id,
            "endpoint_manifest_id": self.endpoint_manifest_id,
            "security_evidence_id": self.security_evidence_id,
            "request_contract_fingerprint": self.request_contract_fingerprint,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
            "raw_url_persisted": False,
            "query_values_persisted": False,
            "headers_persisted": False,
            "secret_material_persisted": False,
        }


def build_provider_network_binding_evidence(
    *,
    run_id: str,
    provider_key: str,
    permit_id: str,
    endpoint_manifest_id: str,
    security_evidence_id: str,
    request_contract_fingerprint: str,
    outcome: str,
    created_at: datetime,
) -> ProviderNetworkBindingEvidence:
    if outcome not in {"COMPLETED", "FAILED"}:
        raise ValueError("INVALID_NETWORK_BINDING_OUTCOME")
    created_at = _aware(created_at)
    base = {
        "schema": "matrix.provider-network-binding-id/1",
        "run_id": run_id,
        "provider_key": provider_key,
        "permit_id": permit_id,
        "endpoint_manifest_id": endpoint_manifest_id,
        "security_evidence_id": security_evidence_id,
        "request_contract_fingerprint": request_contract_fingerprint,
        "outcome": outcome,
        "created_at": created_at.isoformat(),
        "raw_url_persisted": False,
        "query_values_persisted": False,
        "headers_persisted": False,
        "secret_material_persisted": False,
    }
    return ProviderNetworkBindingEvidence(
        evidence_id=_sha(base),
        run_id=run_id,
        provider_key=provider_key,
        permit_id=permit_id,
        endpoint_manifest_id=endpoint_manifest_id,
        security_evidence_id=security_evidence_id,
        request_contract_fingerprint=request_contract_fingerprint,
        outcome=outcome,
        created_at=created_at,
    )


class SQLiteProviderNetworkBindingEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS network_binding (
                    evidence_id TEXT PRIMARY KEY,
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

    def record(self, evidence: ProviderNetworkBindingEvidence) -> str:
        rebuilt = build_provider_network_binding_evidence(
            run_id=evidence.run_id,
            provider_key=evidence.provider_key,
            permit_id=evidence.permit_id,
            endpoint_manifest_id=evidence.endpoint_manifest_id,
            security_evidence_id=evidence.security_evidence_id,
            request_contract_fingerprint=evidence.request_contract_fingerprint,
            outcome=evidence.outcome,
            created_at=evidence.created_at,
        )
        if rebuilt != evidence:
            raise ValueError("NETWORK_BINDING_DERIVATION_MISMATCH")

        payload_json = _json(evidence.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO network_binding (
                    evidence_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    payload_json,
                    payload_sha,
                ),
            )
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM network_binding
                WHERE evidence_id = ?
                """,
                (evidence.evidence_id,),
            ).fetchone()

        if row != (payload_json, payload_sha):
            raise ValueError("NETWORK_BINDING_MUTATION_VIOLATION")
        return evidence.evidence_id

    def get_verified(
        self,
        evidence_id: str,
    ) -> ProviderNetworkBindingEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM network_binding
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

        if row is None:
            return None

        payload_json, payload_sha = row
        if sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha:
            raise ValueError("NETWORK_BINDING_INTEGRITY_FAILURE")

        payload = json.loads(payload_json)
        rebuilt = build_provider_network_binding_evidence(
            run_id=payload["run_id"],
            provider_key=payload["provider_key"],
            permit_id=payload["permit_id"],
            endpoint_manifest_id=payload["endpoint_manifest_id"],
            security_evidence_id=payload["security_evidence_id"],
            request_contract_fingerprint=payload[
                "request_contract_fingerprint"
            ],
            outcome=payload["outcome"],
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

        if (
            rebuilt.evidence_id != evidence_id
            or rebuilt.payload() != payload
        ):
            raise ValueError("NETWORK_BINDING_REDERIVATION_FAILURE")

        return rebuilt

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            evidence_ids = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT evidence_id
                    FROM network_binding
                    ORDER BY evidence_id
                    """
                ).fetchall()
            ]

        try:
            return all(
                self.get_verified(evidence_id) is not None
                for evidence_id in evidence_ids
            )
        except ValueError:
            return False


class BindingAuditPinnedHttpsTransport(MatrixPinnedHttpsTransport):
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True

    def __init__(
        self,
        *,
        inner: MatrixPinnedHttpsTransport,
        binding_store: SQLiteProviderNetworkBindingEvidenceStore,
        collector: ProviderNetworkBindingCollector,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(inner, MatrixPinnedHttpsTransport):
            raise ValueError("PINNED_HTTPS_TRANSPORT_REQUIRED")
        self.inner = inner
        self.binding_store = binding_store
        self.collector = collector
        self.clock = clock

    def _persist(
        self,
        *,
        permit,
        request_contract_fingerprint: str,
        outcome: str,
    ) -> None:
        evidence = build_provider_network_binding_evidence(
            run_id=permit.run_id,
            provider_key=permit.provider_key,
            permit_id=permit.permit_id,
            endpoint_manifest_id=permit.endpoint_manifest_id,
            security_evidence_id=permit.security_evidence_id,
            request_contract_fingerprint=request_contract_fingerprint,
            outcome=outcome,
            created_at=self.clock(),
        )
        self.collector.record(
            self.binding_store.record(evidence)
        )

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
        permit = kwargs.get("matrix_permit")
        request_contract_fingerprint = kwargs.get(
            "matrix_request_contract_fingerprint"
        )

        if permit is None:
            raise ValueError("NETWORK_PERMIT_CONTEXT_REQUIRED")
        if (
            not isinstance(request_contract_fingerprint, str)
            or len(request_contract_fingerprint) != 64
        ):
            raise ValueError("REQUEST_CONTRACT_FINGERPRINT_REQUIRED")

        try:
            response = self.inner.get_pinned(
                url=url,
                original_host=original_host,
                resolved_ips=resolved_ips,
                allow_redirects=allow_redirects,
                verify=verify,
                **kwargs,
            )
        except Exception:
            self._persist(
                permit=permit,
                request_contract_fingerprint=request_contract_fingerprint,
                outcome="FAILED",
            )
            raise

        self._persist(
            permit=permit,
            request_contract_fingerprint=request_contract_fingerprint,
            outcome="COMPLETED",
        )
        return response


@dataclass(frozen=True)
class ProviderNetworkReconciliation:
    run_id: str
    ok: bool
    binding_evidence_ids: tuple[str, ...]
    errors: tuple[str, ...]


def reconcile_provider_network_bindings(
    *,
    run_id: str,
    audit_ledger,
    binding_store: SQLiteProviderNetworkBindingEvidenceStore,
    network_permit_store,
    network_call_evidence_store,
) -> ProviderNetworkReconciliation:
    errors: list[str] = []

    if not binding_store.audit_integrity():
        errors.append("NETWORK_BINDING_STORE_INTEGRITY_FAILED")
    if not network_permit_store.audit_integrity():
        errors.append("NETWORK_PERMIT_STORE_INTEGRITY_FAILED")
    if not network_call_evidence_store.audit_integrity():
        errors.append("NETWORK_CALL_EVIDENCE_INTEGRITY_FAILED")

    events = tuple(audit_ledger.list_events(run_id))
    terminal_events = [
        event
        for event in events
        if event.get("event_type")
        in {"PROVIDER_CALL_COMPLETED", "PROVIDER_CALL_FAILED"}
    ]

    all_ids: list[str] = []

    for event in terminal_events:
        payload = event.get("event_payload")
        if not isinstance(payload, Mapping):
            errors.append("INVALID_PROVIDER_CALL_TERMINAL_PAYLOAD")
            continue

        binding_ids = payload.get("network_binding_evidence_ids")
        if not isinstance(binding_ids, list):
            errors.append("NETWORK_BINDING_EVIDENCE_IDS_REQUIRED")
            continue

        consumed = payload.get("consumed_request_units")
        if (
            isinstance(consumed, int)
            and not isinstance(consumed, bool)
            and consumed >= 0
            and consumed != len(binding_ids)
        ):
            errors.append("NETWORK_BINDING_CONSUMPTION_MISMATCH")

        for evidence_id in binding_ids:
            evidence = binding_store.get_verified(evidence_id)
            if evidence is None:
                errors.append("NETWORK_BINDING_EVIDENCE_MISSING")
                continue

            if evidence.run_id != run_id:
                errors.append("NETWORK_BINDING_RUN_MISMATCH")

            if evidence.provider_key != payload.get("provider_key"):
                errors.append("NETWORK_BINDING_PROVIDER_MISMATCH")

            permit = network_permit_store.get_verified(
                evidence.permit_id
            )
            if permit is None:
                errors.append("NETWORK_BINDING_PERMIT_MISSING")
                continue

            if (
                permit.get("run_id") != evidence.run_id
                or permit.get("provider_key") != evidence.provider_key
                or permit.get("endpoint_manifest_id")
                != evidence.endpoint_manifest_id
                or permit.get("security_evidence_id")
                != evidence.security_evidence_id
            ):
                errors.append("NETWORK_BINDING_PERMIT_MISMATCH")

            network_events = (
                network_call_evidence_store.list_verified_events_for_permit(
                    evidence.permit_id
                )
            )
            terminal_network_events = [
                item
                for item in network_events
                if item.get("event_type")
                in {"NETWORK_CALL_COMPLETED", "NETWORK_CALL_FAILED"}
            ]

            if len(terminal_network_events) != 1:
                errors.append("NETWORK_BINDING_NETWORK_TERMINAL_COUNT")
            else:
                expected_outcome = (
                    "COMPLETED"
                    if terminal_network_events[0]["event_type"]
                    == "NETWORK_CALL_COMPLETED"
                    else "FAILED"
                )
                if expected_outcome != evidence.outcome:
                    errors.append("NETWORK_BINDING_OUTCOME_MISMATCH")

            all_ids.append(evidence_id)

    return ProviderNetworkReconciliation(
        run_id=run_id,
        ok=not errors,
        binding_evidence_ids=tuple(all_ids),
        errors=tuple(errors),
    )
