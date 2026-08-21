from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

from app.core.governed_provider_http import MatrixPinnedHttpsTransport
from app.core.provider_request_contract import (
    build_provider_request_authorization_fingerprint,
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
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


class ProviderNetworkBindingCollector:
    def __init__(self) -> None:
        self._active_queue_fingerprint: str | None = None
        self._evidence_ids: list[str] = []

    def begin(self, queue_item_fingerprint: str) -> None:
        if self._active_queue_fingerprint is not None:
            raise ValueError("NETWORK_BINDING_SCOPE_ALREADY_ACTIVE")
        self._active_queue_fingerprint = _hex64(
            "QUEUE_ITEM_FINGERPRINT",
            queue_item_fingerprint,
        )
        self._evidence_ids = []

    def require_active(self) -> str:
        if self._active_queue_fingerprint is None:
            raise ValueError("NETWORK_BINDING_SCOPE_REQUIRED")
        return self._active_queue_fingerprint

    def record(self, evidence_id: str) -> None:
        self.require_active()
        self._evidence_ids.append(
            _hex64(
                "NETWORK_BINDING_EVIDENCE_ID",
                evidence_id,
            )
        )

    def finish(self, queue_item_fingerprint: str) -> tuple[str, ...]:
        validated = _hex64(
            "QUEUE_ITEM_FINGERPRINT",
            queue_item_fingerprint,
        )
        if self._active_queue_fingerprint != validated:
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
    queue_item_fingerprint: str
    permit_id: str
    endpoint_manifest_id: str
    security_evidence_id: str
    request_contract_id: str
    request_contract_fingerprint: str
    request_path: str
    request_parameter_names: tuple[str, ...]
    request_parameter_values_fingerprint: str
    secret_reference_fingerprint: str
    outcome: str
    created_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-network-binding/2",
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "provider_key": self.provider_key,
            "queue_item_fingerprint": self.queue_item_fingerprint,
            "permit_id": self.permit_id,
            "endpoint_manifest_id": self.endpoint_manifest_id,
            "security_evidence_id": self.security_evidence_id,
            "request_contract_id": self.request_contract_id,
            "request_contract_fingerprint": self.request_contract_fingerprint,
            "request_path": self.request_path,
            "request_parameter_names": list(self.request_parameter_names),
            "request_parameter_values_fingerprint": (
                self.request_parameter_values_fingerprint
            ),
            "secret_reference_fingerprint": self.secret_reference_fingerprint,
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
    queue_item_fingerprint: str,
    permit_id: str,
    endpoint_manifest_id: str,
    security_evidence_id: str,
    request_contract_id: str,
    request_contract_fingerprint: str,
    request_path: str,
    request_parameter_names: tuple[str, ...],
    request_parameter_values_fingerprint: str,
    secret_reference_fingerprint: str,
    outcome: str,
    created_at: datetime,
) -> ProviderNetworkBindingEvidence:
    if outcome not in {"COMPLETED", "FAILED"}:
        raise ValueError("INVALID_NETWORK_BINDING_OUTCOME")
    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if (
        not isinstance(request_path, str)
        or not request_path.startswith("/")
        or "?" in request_path
        or "#" in request_path
    ):
        raise ValueError("INVALID_REQUEST_PATH")

    names = tuple(sorted(str(name) for name in request_parameter_names))
    if len(set(names)) != len(names):
        raise ValueError("DUPLICATE_REQUEST_PARAMETER_NAME")

    created_at = _aware(created_at)

    values = {
        "run_id": _hex64("RUN_ID", run_id),
        "queue_item_fingerprint": _hex64(
            "QUEUE_ITEM_FINGERPRINT",
            queue_item_fingerprint,
        ),
        "permit_id": _hex64("PERMIT_ID", permit_id),
        "endpoint_manifest_id": _hex64(
            "ENDPOINT_MANIFEST_ID",
            endpoint_manifest_id,
        ),
        "security_evidence_id": _hex64(
            "SECURITY_EVIDENCE_ID",
            security_evidence_id,
        ),
        "request_contract_id": _hex64(
            "REQUEST_CONTRACT_ID",
            request_contract_id,
        ),
        "request_contract_fingerprint": _hex64(
            "REQUEST_CONTRACT_FINGERPRINT",
            request_contract_fingerprint,
        ),
        "request_parameter_values_fingerprint": _hex64(
            "REQUEST_PARAMETER_VALUES_FINGERPRINT",
            request_parameter_values_fingerprint,
        ),
        "secret_reference_fingerprint": _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            secret_reference_fingerprint,
        ),
    }

    base = {
        "schema": "matrix.provider-network-binding-id/2",
        "run_id": values["run_id"],
        "provider_key": provider_key,
        "queue_item_fingerprint": values["queue_item_fingerprint"],
        "permit_id": values["permit_id"],
        "endpoint_manifest_id": values["endpoint_manifest_id"],
        "security_evidence_id": values["security_evidence_id"],
        "request_contract_id": values["request_contract_id"],
        "request_contract_fingerprint": values["request_contract_fingerprint"],
        "request_path": request_path,
        "request_parameter_names": list(names),
        "request_parameter_values_fingerprint": (
            values["request_parameter_values_fingerprint"]
        ),
        "secret_reference_fingerprint": values["secret_reference_fingerprint"],
        "outcome": outcome,
        "created_at": created_at.isoformat(),
        "raw_url_persisted": False,
        "query_values_persisted": False,
        "headers_persisted": False,
        "secret_material_persisted": False,
    }

    return ProviderNetworkBindingEvidence(
        evidence_id=_sha(base),
        run_id=values["run_id"],
        provider_key=provider_key,
        queue_item_fingerprint=values["queue_item_fingerprint"],
        permit_id=values["permit_id"],
        endpoint_manifest_id=values["endpoint_manifest_id"],
        security_evidence_id=values["security_evidence_id"],
        request_contract_id=values["request_contract_id"],
        request_contract_fingerprint=values["request_contract_fingerprint"],
        request_path=request_path,
        request_parameter_names=names,
        request_parameter_values_fingerprint=(
            values["request_parameter_values_fingerprint"]
        ),
        secret_reference_fingerprint=values["secret_reference_fingerprint"],
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
            queue_item_fingerprint=evidence.queue_item_fingerprint,
            permit_id=evidence.permit_id,
            endpoint_manifest_id=evidence.endpoint_manifest_id,
            security_evidence_id=evidence.security_evidence_id,
            request_contract_id=evidence.request_contract_id,
            request_contract_fingerprint=evidence.request_contract_fingerprint,
            request_path=evidence.request_path,
            request_parameter_names=evidence.request_parameter_names,
            request_parameter_values_fingerprint=(
                evidence.request_parameter_values_fingerprint
            ),
            secret_reference_fingerprint=evidence.secret_reference_fingerprint,
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
            queue_item_fingerprint=payload["queue_item_fingerprint"],
            permit_id=payload["permit_id"],
            endpoint_manifest_id=payload["endpoint_manifest_id"],
            security_evidence_id=payload["security_evidence_id"],
            request_contract_id=payload["request_contract_id"],
            request_contract_fingerprint=payload["request_contract_fingerprint"],
            request_path=payload["request_path"],
            request_parameter_names=tuple(
                payload["request_parameter_names"]
            ),
            request_parameter_values_fingerprint=(
                payload["request_parameter_values_fingerprint"]
            ),
            secret_reference_fingerprint=payload["secret_reference_fingerprint"],
            outcome=payload["outcome"],
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

        if rebuilt.evidence_id != evidence_id or rebuilt.payload() != payload:
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
        queue_item_fingerprint: str,
        request_contract_id: str,
        request_contract_fingerprint: str,
        request_path: str,
        request_parameter_names: tuple[str, ...],
        request_parameter_values_fingerprint: str,
        secret_reference_fingerprint: str,
        outcome: str,
    ) -> None:
        evidence = build_provider_network_binding_evidence(
            run_id=permit.run_id,
            provider_key=permit.provider_key,
            queue_item_fingerprint=queue_item_fingerprint,
            permit_id=permit.permit_id,
            endpoint_manifest_id=permit.endpoint_manifest_id,
            security_evidence_id=permit.security_evidence_id,
            request_contract_id=request_contract_id,
            request_contract_fingerprint=request_contract_fingerprint,
            request_path=request_path,
            request_parameter_names=request_parameter_names,
            request_parameter_values_fingerprint=(
                request_parameter_values_fingerprint
            ),
            secret_reference_fingerprint=secret_reference_fingerprint,
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
        if permit is None:
            raise ValueError("NETWORK_PERMIT_CONTEXT_REQUIRED")

        queue_item_fingerprint = self.collector.require_active()
        request_contract_id = _hex64(
            "REQUEST_CONTRACT_ID",
            kwargs.get("matrix_request_contract_id"),
        )
        request_contract_fingerprint = _hex64(
            "REQUEST_CONTRACT_FINGERPRINT",
            kwargs.get("matrix_request_contract_fingerprint"),
        )
        request_path = kwargs.get("matrix_request_path")
        if (
            not isinstance(request_path, str)
            or not request_path.startswith("/")
            or "?" in request_path
            or "#" in request_path
        ):
            raise ValueError("REQUEST_PATH_REQUIRED")

        raw_names = kwargs.get("matrix_request_parameter_names")
        if not isinstance(raw_names, tuple):
            raise ValueError("REQUEST_PARAMETER_NAMES_REQUIRED")
        request_parameter_names = tuple(sorted(str(item) for item in raw_names))
        if len(set(request_parameter_names)) != len(request_parameter_names):
            raise ValueError("DUPLICATE_REQUEST_PARAMETER_NAME")

        values_fp = _hex64(
            "REQUEST_PARAMETER_VALUES_FINGERPRINT",
            kwargs.get("matrix_request_parameter_values_fingerprint"),
        )
        secret_fp = _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            kwargs.get("matrix_request_secret_reference_fingerprint"),
        )

        persist = {
            "permit": permit,
            "queue_item_fingerprint": queue_item_fingerprint,
            "request_contract_id": request_contract_id,
            "request_contract_fingerprint": request_contract_fingerprint,
            "request_path": request_path,
            "request_parameter_names": request_parameter_names,
            "request_parameter_values_fingerprint": values_fp,
            "secret_reference_fingerprint": secret_fp,
        }

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
                **persist,
                outcome="FAILED",
            )
            raise

        self._persist(
            **persist,
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
    request_contract_registry,
) -> ProviderNetworkReconciliation:
    errors: list[str] = []

    if not binding_store.audit_integrity():
        errors.append("NETWORK_BINDING_STORE_INTEGRITY_FAILED")
    if not network_permit_store.audit_integrity():
        errors.append("NETWORK_PERMIT_STORE_INTEGRITY_FAILED")
    if not network_call_evidence_store.audit_integrity():
        errors.append("NETWORK_CALL_EVIDENCE_INTEGRITY_FAILED")
    if not request_contract_registry.audit_integrity():
        errors.append("REQUEST_CONTRACT_REGISTRY_INTEGRITY_FAILED")

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

        queue_item_fingerprint = payload.get("queue_item_fingerprint")
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
            if evidence.queue_item_fingerprint != queue_item_fingerprint:
                errors.append("NETWORK_BINDING_QUEUE_ITEM_MISMATCH")

            permit = network_permit_store.get_verified(evidence.permit_id)
            if permit is None:
                errors.append("NETWORK_BINDING_PERMIT_MISSING")
                continue

            if (
                permit.get("run_id") != evidence.run_id
                or permit.get("provider_key") != evidence.provider_key
                or permit.get("endpoint_manifest_id") != evidence.endpoint_manifest_id
                or permit.get("security_evidence_id") != evidence.security_evidence_id
            ):
                errors.append("NETWORK_BINDING_PERMIT_MISMATCH")

            consumed_at = permit.get("consumed_at")
            if not isinstance(consumed_at, str):
                errors.append("NETWORK_PERMIT_NOT_CONSUMED")
            else:
                try:
                    parsed_consumed = datetime.fromisoformat(consumed_at)
                except Exception:
                    errors.append("NETWORK_PERMIT_CONSUMED_AT_INVALID")
                else:
                    if (
                        parsed_consumed.tzinfo is None
                        or parsed_consumed.utcoffset() is None
                    ):
                        errors.append("NETWORK_PERMIT_CONSUMED_AT_NAIVE")

            contract = request_contract_registry.get_verified(
                evidence.request_contract_id
            )
            if contract is None:
                errors.append("REQUEST_CONTRACT_EVIDENCE_MISSING")
            else:
                if (
                    contract.provider_key != evidence.provider_key
                    or contract.sport != permit.get("sport")
                    or contract.method != permit.get("method")
                    or contract.path != evidence.request_path
                    or contract.secret_reference_fingerprint
                    != evidence.secret_reference_fingerprint
                ):
                    errors.append("REQUEST_CONTRACT_NETWORK_BINDING_MISMATCH")

                rule_names = {
                    rule.name
                    for rule in contract.parameter_rules
                }
                required_names = {
                    rule.name
                    for rule in contract.parameter_rules
                    if rule.required
                }
                actual_names = set(evidence.request_parameter_names)

                if not actual_names.issubset(rule_names):
                    errors.append("REQUEST_PARAMETER_NAME_NOT_IN_CONTRACT")
                if not required_names.issubset(actual_names):
                    errors.append("REQUEST_REQUIRED_PARAMETER_MISSING")

                expected_authorization = (
                    build_provider_request_authorization_fingerprint(
                        contract_id=evidence.request_contract_id,
                        provider_key=evidence.provider_key,
                        sport=contract.sport,
                        method=contract.method,
                        path=evidence.request_path,
                        parameter_names=evidence.request_parameter_names,
                        parameter_values_fingerprint=(
                            evidence.request_parameter_values_fingerprint
                        ),
                        secret_reference_fingerprint=(
                            evidence.secret_reference_fingerprint
                        ),
                    )
                )
                if (
                    expected_authorization
                    != evidence.request_contract_fingerprint
                ):
                    errors.append("REQUEST_AUTHORIZATION_FINGERPRINT_MISMATCH")

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
                terminal_network = terminal_network_events[0]
                if (
                    terminal_network.get("run_id") not in {None, evidence.run_id}
                    or terminal_network.get("provider_key")
                    not in {None, evidence.provider_key}
                    or terminal_network.get("endpoint_manifest_id")
                    not in {None, evidence.endpoint_manifest_id}
                ):
                    errors.append("NETWORK_CALL_EVIDENCE_BINDING_MISMATCH")

                expected_outcome = (
                    "COMPLETED"
                    if terminal_network["event_type"]
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
