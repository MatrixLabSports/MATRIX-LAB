from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from app.core.governed_provider_request import JitSecretPinnedHttpsTransport
from app.core.pinned_https_transport import StdlibPinnedHttpsTransport
from app.core.provider_network_binding import BindingAuditPinnedHttpsTransport


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


@dataclass(frozen=True)
class NetworkBoundaryCertification:
    status: str
    pinned_tls_transport: bool
    default_production_transport: bool
    request_contract_integrity: bool
    jit_secret_resolution: bool
    provider_network_binding_integrity: bool
    network_permit_integrity: bool
    network_call_evidence_integrity: bool
    real_provider_execution_authorized: bool
    certification_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.network-boundary-certification/1",
            "status": self.status,
            "pinned_tls_transport": self.pinned_tls_transport,
            "default_production_transport": self.default_production_transport,
            "request_contract_integrity": self.request_contract_integrity,
            "jit_secret_resolution": self.jit_secret_resolution,
            "provider_network_binding_integrity": (
                self.provider_network_binding_integrity
            ),
            "network_permit_integrity": self.network_permit_integrity,
            "network_call_evidence_integrity": self.network_call_evidence_integrity,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "real_provider_execution_authorized": False,
            "certification_fingerprint": self.certification_fingerprint,
        }


def _base(
    *,
    status: str,
    pinned_tls_transport: bool,
    default_production_transport: bool,
    request_contract_integrity: bool,
    jit_secret_resolution: bool,
    provider_network_binding_integrity: bool,
    network_permit_integrity: bool,
    network_call_evidence_integrity: bool,
) -> Mapping[str, Any]:
    return {
        "schema": "matrix.network-boundary-certification-id/1",
        "status": status,
        "pinned_tls_transport": pinned_tls_transport,
        "default_production_transport": default_production_transport,
        "request_contract_integrity": request_contract_integrity,
        "jit_secret_resolution": jit_secret_resolution,
        "provider_network_binding_integrity": provider_network_binding_integrity,
        "network_permit_integrity": network_permit_integrity,
        "network_call_evidence_integrity": network_call_evidence_integrity,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "real_provider_execution_authorized": False,
    }


def verify_network_boundary_certification(
    certification: NetworkBoundaryCertification,
) -> NetworkBoundaryCertification:
    if not isinstance(certification, NetworkBoundaryCertification):
        raise ValueError("INVALID_NETWORK_BOUNDARY_CERTIFICATION")

    expected_status = (
        "TECHNICALLY_CERTIFIED_FAIL_CLOSED"
        if all(
            (
                certification.pinned_tls_transport,
                certification.default_production_transport,
                certification.request_contract_integrity,
                certification.jit_secret_resolution,
                certification.provider_network_binding_integrity,
                certification.network_permit_integrity,
                certification.network_call_evidence_integrity,
            )
        )
        else "NOT_CERTIFIED"
    )

    if certification.status != expected_status:
        raise ValueError("NETWORK_CERTIFICATION_STATUS_MISMATCH")

    if certification.real_provider_execution_authorized is not False:
        raise ValueError("REAL_PROVIDER_EXECUTION_MUST_REMAIN_DISABLED")

    expected = _sha(
        _base(
            status=certification.status,
            pinned_tls_transport=certification.pinned_tls_transport,
            default_production_transport=certification.default_production_transport,
            request_contract_integrity=certification.request_contract_integrity,
            jit_secret_resolution=certification.jit_secret_resolution,
            provider_network_binding_integrity=(
                certification.provider_network_binding_integrity
            ),
            network_permit_integrity=certification.network_permit_integrity,
            network_call_evidence_integrity=(
                certification.network_call_evidence_integrity
            ),
        )
    )

    if expected != certification.certification_fingerprint:
        raise ValueError("NETWORK_CERTIFICATION_FINGERPRINT_MISMATCH")
    return certification


def require_real_provider_execution_authorized(
    certification: NetworkBoundaryCertification,
) -> None:
    verify_network_boundary_certification(certification)

    if certification.real_provider_execution_authorized is not True:
        raise ValueError("REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED")

    raise ValueError("REAL_PROVIDER_EXECUTION_SCHEMA_NOT_ACTIVATED")


def certify_controlled_network_boundary(
    *,
    transport,
    request_contract_registry,
    binding_store,
    network_permit_store,
    network_call_evidence_store,
) -> NetworkBoundaryCertification:
    binding_wrapper = isinstance(
        transport,
        BindingAuditPinnedHttpsTransport,
    )
    jit_wrapper = (
        binding_wrapper
        and isinstance(
            transport.inner,
            JitSecretPinnedHttpsTransport,
        )
    )
    base_transport = transport.inner.inner if jit_wrapper else None
    pinned_tls_transport = isinstance(
        base_transport,
        StdlibPinnedHttpsTransport,
    )
    default_production_transport = (
        pinned_tls_transport
        and bool(
            getattr(
                base_transport,
                "production_default_transport",
                False,
            )
        )
    )

    request_contract_integrity = request_contract_registry.audit_integrity()
    provider_network_binding_integrity = binding_store.audit_integrity()
    network_permit_integrity = network_permit_store.audit_integrity()
    network_call_evidence_integrity = (
        network_call_evidence_store.audit_integrity()
    )

    technical_ok = all(
        (
            binding_wrapper,
            jit_wrapper,
            pinned_tls_transport,
            default_production_transport,
            request_contract_integrity,
            provider_network_binding_integrity,
            network_permit_integrity,
            network_call_evidence_integrity,
        )
    )
    status = (
        "TECHNICALLY_CERTIFIED_FAIL_CLOSED"
        if technical_ok
        else "NOT_CERTIFIED"
    )

    base = _base(
        status=status,
        pinned_tls_transport=pinned_tls_transport,
        default_production_transport=default_production_transport,
        request_contract_integrity=request_contract_integrity,
        jit_secret_resolution=jit_wrapper,
        provider_network_binding_integrity=provider_network_binding_integrity,
        network_permit_integrity=network_permit_integrity,
        network_call_evidence_integrity=network_call_evidence_integrity,
    )

    certification = NetworkBoundaryCertification(
        status=status,
        pinned_tls_transport=pinned_tls_transport,
        default_production_transport=default_production_transport,
        request_contract_integrity=request_contract_integrity,
        jit_secret_resolution=jit_wrapper,
        provider_network_binding_integrity=provider_network_binding_integrity,
        network_permit_integrity=network_permit_integrity,
        network_call_evidence_integrity=network_call_evidence_integrity,
        real_provider_execution_authorized=False,
        certification_fingerprint=_sha(base),
    )
    return verify_network_boundary_certification(certification)
