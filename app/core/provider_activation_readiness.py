from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from app.core.controlled_network_certification import (
    NetworkBoundaryCertification,
    verify_network_boundary_certification,
)
from app.core.governed_provider_request import (
    JitSecretPinnedHttpsTransport,
)
from app.core.provider_connector_trust import (
    ProviderConnectorTrustDecision,
    require_trusted_production_connector,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
)
from app.core.provider_endpoint_authorization import (
    SQLiteProviderEndpointAuthorizationRegistry,
)
from app.core.provider_legal_evidence import (
    SQLiteProviderLegalEvidenceStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    SecretReference,
    resolve_secret_runtime,
)


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
    return sha256(
        _json(value).encode("utf-8")
    ).hexdigest()


def _query_keys(contract) -> tuple[str, ...]:
    keys: list[str] = []

    for rule in tuple(
        getattr(
            contract,
            "parameter_rules",
            (),
        )
    ):
        name = (
            getattr(
                rule,
                "name",
                None,
            )
            or getattr(
                rule,
                "parameter_name",
                None,
            )
            or getattr(
                rule,
                "key",
                None,
            )
        )

        if not isinstance(
            name,
            str,
        ) or not name:
            raise ValueError(
                "REQUEST_CONTRACT_PARAMETER_NAME_REQUIRED"
            )

        keys.append(
            name
        )

    return tuple(
        sorted(
            set(
                keys
            )
        )
    )


@dataclass(frozen=True)
class ProviderActivationReadinessCertification:
    status: str
    network_boundary_certified: bool
    connector_trust_verified: bool
    canonical_secret_resolver: bool
    request_contract_evidence_nonempty: bool
    request_contract_integrity: bool
    contract_endpoint_binding_integrity: bool
    endpoint_manifest_semantics_verified: bool
    legal_evidence_nonempty: bool
    legal_evidence_integrity: bool
    attempt_intent_integrity: bool
    attempt_intent_store_cross_bound: bool
    production_rights_blocked: bool
    real_provider_execution_authorized: bool
    blockers: tuple[str, ...]
    certification_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-activation-readiness-certification/2"
            ),
            "status": self.status,
            "network_boundary_certified": (
                self.network_boundary_certified
            ),
            "connector_trust_verified": (
                self.connector_trust_verified
            ),
            "canonical_secret_resolver": (
                self.canonical_secret_resolver
            ),
            "request_contract_evidence_nonempty": (
                self.request_contract_evidence_nonempty
            ),
            "request_contract_integrity": (
                self.request_contract_integrity
            ),
            "contract_endpoint_binding_integrity": (
                self.contract_endpoint_binding_integrity
            ),
            "endpoint_manifest_semantics_verified": (
                self.endpoint_manifest_semantics_verified
            ),
            "legal_evidence_nonempty": (
                self.legal_evidence_nonempty
            ),
            "legal_evidence_integrity": (
                self.legal_evidence_integrity
            ),
            "attempt_intent_integrity": (
                self.attempt_intent_integrity
            ),
            "attempt_intent_store_cross_bound": (
                self.attempt_intent_store_cross_bound
            ),
            "production_rights_blocked": (
                self.production_rights_blocked
            ),
            "blockers": list(
                self.blockers
            ),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "certification_fingerprint": (
                self.certification_fingerprint
            ),
        }


def _base(
    *,
    status: str,
    network_boundary_certified: bool,
    connector_trust_verified: bool,
    canonical_secret_resolver: bool,
    request_contract_evidence_nonempty: bool,
    request_contract_integrity: bool,
    contract_endpoint_binding_integrity: bool,
    endpoint_manifest_semantics_verified: bool,
    legal_evidence_nonempty: bool,
    legal_evidence_integrity: bool,
    attempt_intent_integrity: bool,
    attempt_intent_store_cross_bound: bool,
    production_rights_blocked: bool,
    blockers: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "schema": (
            "matrix.provider-activation-readiness-certification-id/2"
        ),
        "status": status,
        "network_boundary_certified": (
            network_boundary_certified
        ),
        "connector_trust_verified": (
            connector_trust_verified
        ),
        "canonical_secret_resolver": (
            canonical_secret_resolver
        ),
        "request_contract_evidence_nonempty": (
            request_contract_evidence_nonempty
        ),
        "request_contract_integrity": (
            request_contract_integrity
        ),
        "contract_endpoint_binding_integrity": (
            contract_endpoint_binding_integrity
        ),
        "endpoint_manifest_semantics_verified": (
            endpoint_manifest_semantics_verified
        ),
        "legal_evidence_nonempty": (
            legal_evidence_nonempty
        ),
        "legal_evidence_integrity": (
            legal_evidence_integrity
        ),
        "attempt_intent_integrity": (
            attempt_intent_integrity
        ),
        "attempt_intent_store_cross_bound": (
            attempt_intent_store_cross_bound
        ),
        "production_rights_blocked": (
            production_rights_blocked
        ),
        "blockers": list(
            blockers
        ),
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }


def verify_provider_activation_readiness_certification(
    certification: ProviderActivationReadinessCertification,
) -> ProviderActivationReadinessCertification:
    if not isinstance(
        certification,
        ProviderActivationReadinessCertification,
    ):
        raise ValueError(
            "INVALID_PROVIDER_ACTIVATION_READINESS_CERTIFICATION"
        )

    technical_ready = all(
        (
            certification.network_boundary_certified,
            certification.connector_trust_verified,
            certification.canonical_secret_resolver,
            certification.request_contract_evidence_nonempty,
            certification.request_contract_integrity,
            certification.contract_endpoint_binding_integrity,
            certification.endpoint_manifest_semantics_verified,
            certification.legal_evidence_nonempty,
            certification.legal_evidence_integrity,
            certification.attempt_intent_integrity,
            certification.attempt_intent_store_cross_bound,
        )
    )

    expected_status = (
        "TECHNICALLY_READY_RIGHTS_BLOCKED"
        if (
            technical_ready
            and certification.production_rights_blocked
        )
        else "NOT_READY"
    )

    if certification.status != expected_status:
        raise ValueError(
            "PROVIDER_ACTIVATION_READINESS_STATUS_MISMATCH"
        )

    if (
        certification.real_provider_execution_authorized
        is not False
    ):
        raise ValueError(
            "REAL_PROVIDER_EXECUTION_MUST_REMAIN_DISABLED"
        )

    expected = _sha(
        _base(
            status=certification.status,
            network_boundary_certified=(
                certification.network_boundary_certified
            ),
            connector_trust_verified=(
                certification.connector_trust_verified
            ),
            canonical_secret_resolver=(
                certification.canonical_secret_resolver
            ),
            request_contract_evidence_nonempty=(
                certification.request_contract_evidence_nonempty
            ),
            request_contract_integrity=(
                certification.request_contract_integrity
            ),
            contract_endpoint_binding_integrity=(
                certification.contract_endpoint_binding_integrity
            ),
            endpoint_manifest_semantics_verified=(
                certification.endpoint_manifest_semantics_verified
            ),
            legal_evidence_nonempty=(
                certification.legal_evidence_nonempty
            ),
            legal_evidence_integrity=(
                certification.legal_evidence_integrity
            ),
            attempt_intent_integrity=(
                certification.attempt_intent_integrity
            ),
            attempt_intent_store_cross_bound=(
                certification.attempt_intent_store_cross_bound
            ),
            production_rights_blocked=(
                certification.production_rights_blocked
            ),
            blockers=certification.blockers,
        )
    )

    if (
        expected
        != certification.certification_fingerprint
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_READINESS_FINGERPRINT_MISMATCH"
        )

    return certification


def certify_provider_activation_readiness(
    *,
    network_boundary_certification: NetworkBoundaryCertification,
    governed_transport,
    secret_reference: SecretReference,
    request_contract_registry,
    request_contract_ids: Sequence[str],
    contract_endpoint_binding_store,
    endpoint_authorization_registry,
    endpoint_base_url: str,
    as_of: datetime,
    legal_evidence_store,
    legal_evidence_ids: Sequence[str],
    rights_decision,
    attempt_intent_store,
) -> ProviderActivationReadinessCertification:
    verified_boundary = (
        verify_network_boundary_certification(
            network_boundary_certification
        )
    )

    network_boundary_certified = (
        verified_boundary.status
        == "TECHNICALLY_CERTIFIED_FAIL_CLOSED"
        and verified_boundary.real_provider_execution_authorized
        is False
    )

    binding_wrapper = type(governed_transport) is BindingAuditPinnedHttpsTransport

    jit_wrapper = (
        binding_wrapper
        and type(governed_transport.inner) is JitSecretPinnedHttpsTransport
    )

    authoritative_store_types_bound = all(
        (
            type(request_contract_registry)
            is SQLiteProviderRequestContractRegistry,
            type(contract_endpoint_binding_store)
            is SQLiteProviderContractEndpointBindingStore,
            type(endpoint_authorization_registry)
            is SQLiteProviderEndpointAuthorizationRegistry,
            type(legal_evidence_store)
            is SQLiteProviderLegalEvidenceStore,
            type(attempt_intent_store)
            is SQLiteProviderAttemptIntentStore,
        )
    )

    base_transport = (
        governed_transport.inner.inner
        if jit_wrapper
        else None
    )

    connector_decision: (
        ProviderConnectorTrustDecision
        | None
    ) = None

    if base_transport is not None:
        try:
            connector_decision = (
                require_trusted_production_connector(
                    base_transport
                )
            )
        except ValueError:
            connector_decision = None

    connector_trust_verified = (
        connector_decision is not None
        and connector_decision.trusted_for_production
    )

    canonical_secret_resolver = (
        jit_wrapper
        and governed_transport.inner.resolver
        is resolve_secret_runtime
        and governed_transport.inner.secret_reference
        == secret_reference
    )

    attempt_intent_store_cross_bound = (
        authoritative_store_types_bound
        and binding_wrapper
        and getattr(governed_transport, "attempt_intent_store", None)
        is attempt_intent_store
        and attempt_intent_store is not None
    )

    contract_ids = tuple(
        str(contract_id)
        for contract_id
        in request_contract_ids
    )

    request_contract_evidence_nonempty = (
        bool(contract_ids)
        and len(set(contract_ids))
        == len(contract_ids)
    )

    request_contract_integrity = (
        authoritative_store_types_bound
        and bool(
            request_contract_registry.audit_integrity()
        )
    )

    contract_endpoint_binding_integrity = (
        authoritative_store_types_bound
        and bool(
            contract_endpoint_binding_store.audit_integrity()
        )
    )

    endpoint_manifest_semantics_verified = (
        authoritative_store_types_bound
        and bool(
            endpoint_authorization_registry.audit_integrity()
        )
    )

    parsed_base = urlsplit(
        endpoint_base_url
    )

    if (
        parsed_base.scheme.lower() != "https"
        or not parsed_base.hostname
        or parsed_base.query
        or parsed_base.fragment
        or parsed_base.path not in {"", "/"}
    ):
        endpoint_manifest_semantics_verified = False

    if request_contract_evidence_nonempty and authoritative_store_types_bound:
        for contract_id in contract_ids:
            contract = (
                request_contract_registry.get_verified(
                    contract_id
                )
            )
            binding = (
                contract_endpoint_binding_store.get_verified_by_contract(
                    contract_id
                )
            )

            if (
                contract is None
                or binding is None
                or binding.request_contract_id
                != contract_id
                or binding.provider_key
                != contract.provider_key
                or binding.sport
                != contract.sport
                or binding.path
                != contract.path
                or contract.secret_reference_fingerprint
                != secret_reference.reference_fingerprint
            ):
                request_contract_integrity = False
                contract_endpoint_binding_integrity = False
                endpoint_manifest_semantics_verified = False
                break

            try:
                endpoint_decision = (
                    endpoint_authorization_registry.authorize_request(
                        provider_key=contract.provider_key,
                        sport=contract.sport,
                        method=contract.method,
                        endpoint_url=(
                            endpoint_base_url.rstrip("/")
                            + contract.path
                        ),
                        query_keys=_query_keys(
                            contract
                        ),
                        secret_reference_fingerprint=(
                            secret_reference.reference_fingerprint
                        ),
                        as_of=as_of,
                    )
                )
            except Exception:
                endpoint_manifest_semantics_verified = False
                break

            if (
                endpoint_decision.executable
                is not True
                or endpoint_decision.status
                != "AUTHORIZED"
                or endpoint_decision.manifest_id
                != binding.endpoint_manifest_id
            ):
                endpoint_manifest_semantics_verified = False
                break
    else:
        request_contract_integrity = False
        contract_endpoint_binding_integrity = False
        endpoint_manifest_semantics_verified = False

    legal_ids = tuple(
        str(evidence_id)
        for evidence_id
        in legal_evidence_ids
    )

    legal_evidence_nonempty = (
        bool(legal_ids)
        and len(set(legal_ids))
        == len(legal_ids)
    )

    legal_evidence_integrity = (
        authoritative_store_types_bound
        and bool(
            legal_evidence_store.audit_integrity()
        )
    )

    legal_kinds: set[str] = set()

    if legal_evidence_nonempty and authoritative_store_types_bound:
        for evidence_id in legal_ids:
            try:
                evidence = (
                    legal_evidence_store.get_verified(
                        evidence_id
                    )
                )
            except Exception:
                evidence = None

            if (
                evidence is None
                or evidence.verification_status
                != "HUMAN_VERIFIED"
            ):
                legal_evidence_integrity = False
                break

            legal_kinds.add(
                evidence.evidence_kind
            )

        if "PROVIDER_TERMS" not in legal_kinds:
            legal_evidence_integrity = False
    else:
        legal_evidence_integrity = False

    attempt_intent_integrity = (
        authoritative_store_types_bound
        and attempt_intent_store is not None
        and bool(
            attempt_intent_store.audit_integrity()
        )
    )

    production_rights_blocked = (
        rights_decision is not None
        and rights_decision.authorized
        is False
        and (
            "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED"
            in rights_decision.blockers
            or "PROVIDER_RIGHTS_NOT_AUTHORIZED"
            in rights_decision.blockers
        )
    )

    blockers: list[str] = []

    checks = (
        (
            authoritative_store_types_bound,
            "AUTHORITATIVE_ACTIVATION_STORE_TYPES_REQUIRED",
        ),
        (
            network_boundary_certified,
            "NETWORK_BOUNDARY_NOT_CERTIFIED",
        ),
        (
            connector_trust_verified,
            "CONNECTOR_TRUST_NOT_VERIFIED",
        ),
        (
            canonical_secret_resolver,
            "CANONICAL_SECRET_RESOLVER_REQUIRED",
        ),
        (
            request_contract_evidence_nonempty,
            "NONEMPTY_REQUEST_CONTRACT_EVIDENCE_REQUIRED",
        ),
        (
            request_contract_integrity,
            "REQUEST_CONTRACT_INTEGRITY_FAILED",
        ),
        (
            contract_endpoint_binding_integrity,
            "CONTRACT_ENDPOINT_BINDING_INTEGRITY_FAILED",
        ),
        (
            endpoint_manifest_semantics_verified,
            "ENDPOINT_MANIFEST_SEMANTIC_AUTHORIZATION_REQUIRED",
        ),
        (
            legal_evidence_nonempty,
            "NONEMPTY_LEGAL_EVIDENCE_REQUIRED",
        ),
        (
            legal_evidence_integrity,
            "LEGAL_EVIDENCE_INTEGRITY_FAILED",
        ),
        (
            attempt_intent_integrity,
            "ATTEMPT_INTENT_INTEGRITY_FAILED",
        ),
        (
            attempt_intent_store_cross_bound,
            "ATTEMPT_INTENT_STORE_CROSS_BINDING_REQUIRED",
        ),
        (
            production_rights_blocked,
            "PRODUCTION_RIGHTS_MUST_REMAIN_BLOCKED",
        ),
    )

    for ok, reason in checks:
        if not ok:
            blockers.append(
                reason
            )

    technical_ready = all(
        ok
        for ok, _
        in checks[:-1]
    )

    status = (
        "TECHNICALLY_READY_RIGHTS_BLOCKED"
        if (
            technical_ready
            and production_rights_blocked
        )
        else "NOT_READY"
    )

    base = _base(
        status=status,
        network_boundary_certified=network_boundary_certified,
        connector_trust_verified=connector_trust_verified,
        canonical_secret_resolver=canonical_secret_resolver,
        request_contract_evidence_nonempty=(
            request_contract_evidence_nonempty
        ),
        request_contract_integrity=request_contract_integrity,
        contract_endpoint_binding_integrity=(
            contract_endpoint_binding_integrity
        ),
        endpoint_manifest_semantics_verified=(
            endpoint_manifest_semantics_verified
        ),
        legal_evidence_nonempty=legal_evidence_nonempty,
        legal_evidence_integrity=legal_evidence_integrity,
        attempt_intent_integrity=attempt_intent_integrity,
        attempt_intent_store_cross_bound=(
            attempt_intent_store_cross_bound
        ),
        production_rights_blocked=production_rights_blocked,
        blockers=tuple(blockers),
    )

    certification = (
        ProviderActivationReadinessCertification(
            status=status,
            network_boundary_certified=network_boundary_certified,
            connector_trust_verified=connector_trust_verified,
            canonical_secret_resolver=canonical_secret_resolver,
            request_contract_evidence_nonempty=(
                request_contract_evidence_nonempty
            ),
            request_contract_integrity=request_contract_integrity,
            contract_endpoint_binding_integrity=(
                contract_endpoint_binding_integrity
            ),
            endpoint_manifest_semantics_verified=(
                endpoint_manifest_semantics_verified
            ),
            legal_evidence_nonempty=legal_evidence_nonempty,
            legal_evidence_integrity=legal_evidence_integrity,
            attempt_intent_integrity=attempt_intent_integrity,
            attempt_intent_store_cross_bound=(
                attempt_intent_store_cross_bound
            ),
            production_rights_blocked=production_rights_blocked,
            real_provider_execution_authorized=False,
            blockers=tuple(blockers),
            certification_fingerprint=_sha(base),
        )
    )

    return (
        verify_provider_activation_readiness_certification(
            certification
        )
    )


def require_provider_activation_authorized(
    certification: ProviderActivationReadinessCertification,
) -> None:
    verify_provider_activation_readiness_certification(
        certification
    )

    if (
        certification.real_provider_execution_authorized
        is not True
    ):
        raise ValueError(
            "REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED"
        )

    raise ValueError(
        "PROVIDER_ACTIVATION_SCHEMA_NOT_ENABLED"
    )
