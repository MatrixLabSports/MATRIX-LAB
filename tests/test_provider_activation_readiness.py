from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.controlled_network_certification import (
    certify_controlled_network_boundary,
)
from app.core.governed_provider_http import (
    SQLiteProviderNetworkCallEvidenceStore,
)
from app.core.governed_provider_request import (
    JitSecretPinnedHttpsTransport,
)
from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)
from app.core.provider_activation_readiness import (
    certify_provider_activation_readiness,
    require_provider_activation_authorized,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
    build_provider_contract_endpoint_binding,
)
from app.core.provider_legal_evidence import (
    SQLiteProviderLegalEvidenceStore,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_network_execution_authorization import (
    SQLiteProviderNetworkPermitStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.request_contracts import (
    build_api_football_request_contracts,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def _contract(
    *,
    secret,
):
    contracts = (
        build_api_football_request_contracts(
            secret_reference_fingerprint=(
                secret.reference_fingerprint
            ),
            valid_from=NOW,
        )
    )

    return contracts[
        "fixture_by_id"
    ]


def _rights_blocked():
    return SimpleNamespace(
        authorized=False,
        blockers=(
            "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED",
        ),
    )


def test_activation_readiness_requires_canonical_secret_resolver_and_nonempty_contracts(
    tmp_path,
):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable=(
            "MATRIX_API_FOOTBALL_KEY"
        ),
        secret_type="API_KEY",
    )

    contract_registry = (
        SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        )
    )

    contract = _contract(
        secret=secret
    )

    contract_registry.register(
        contract
    )

    endpoint_store = (
        SQLiteProviderContractEndpointBindingStore(
            tmp_path / "endpoint.db"
        )
    )

    endpoint_store.register(
        build_provider_contract_endpoint_binding(
            provider_key="api_football",
            sport="football",
            request_contract_id=(
                contract.contract_id
            ),
            endpoint_manifest_id="1" * 64,
            path=contract.path,
            valid_from=NOW,
            valid_until=None,
        )
    )

    binding_store = (
        SQLiteProviderNetworkBindingEvidenceStore(
            tmp_path / "binding.db"
        )
    )

    permit_store = (
        SQLiteProviderNetworkPermitStore(
            tmp_path / "permit.db"
        )
    )

    call_store = (
        SQLiteProviderNetworkCallEvidenceStore(
            tmp_path / "call.db"
        )
    )

    attempt_intent_store = (
        SQLiteProviderAttemptIntentStore(
            tmp_path / "intent.db"
        )
    )

    base = (
        StdlibPinnedHttpsTransport()
    )

    jit = (
        JitSecretPinnedHttpsTransport(
            inner=base,
            secret_reference=secret,
            auth_header_name=(
                "x-apisports-key"
            ),
        )
    )

    governed = (
        BindingAuditPinnedHttpsTransport(
            inner=jit,
            binding_store=binding_store,
            collector=(
                ProviderNetworkBindingCollector()
            ),
            clock=lambda: NOW,
            attempt_intent_store=(
                attempt_intent_store
            ),
        )
    )

    boundary = (
        certify_controlled_network_boundary(
            transport=governed,
            request_contract_registry=(
                contract_registry
            ),
            binding_store=(
                binding_store
            ),
            network_permit_store=(
                permit_store
            ),
            network_call_evidence_store=(
                call_store
            ),
        )
    )

    certification = (
        certify_provider_activation_readiness(
            network_boundary_certification=(
                boundary
            ),
            governed_transport=(
                governed
            ),
            secret_reference=secret,
            request_contract_registry=(
                contract_registry
            ),
            request_contract_ids=(
                contract.contract_id,
            ),
            contract_endpoint_binding_store=(
                endpoint_store
            ),
            legal_evidence_store=(
                SQLiteProviderLegalEvidenceStore(
                    tmp_path / "legal.db"
                )
            ),
            rights_decision=(
                _rights_blocked()
            ),
            attempt_intent_store=(
                attempt_intent_store
            ),
        )
    )

    assert (
        certification.status
        == "TECHNICALLY_READY_RIGHTS_BLOCKED"
    )
    assert (
        certification.canonical_secret_resolver
        is True
    )
    assert (
        certification.request_contract_evidence_nonempty
        is True
    )
    assert (
        certification.real_provider_execution_authorized
        is False
    )

    with pytest.raises(
        ValueError,
        match="REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED",
    ):
        require_provider_activation_authorized(
            certification
        )


def test_empty_request_contract_evidence_is_not_ready(
    tmp_path,
):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable=(
            "MATRIX_API_FOOTBALL_KEY"
        ),
        secret_type="API_KEY",
    )

    contract_registry = (
        SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        )
    )

    binding_store = (
        SQLiteProviderNetworkBindingEvidenceStore(
            tmp_path / "binding.db"
        )
    )

    permit_store = (
        SQLiteProviderNetworkPermitStore(
            tmp_path / "permit.db"
        )
    )

    call_store = (
        SQLiteProviderNetworkCallEvidenceStore(
            tmp_path / "call.db"
        )
    )

    attempt_intent_store = (
        SQLiteProviderAttemptIntentStore(
            tmp_path / "intent.db"
        )
    )

    governed = (
        BindingAuditPinnedHttpsTransport(
            inner=(
                JitSecretPinnedHttpsTransport(
                    inner=(
                        StdlibPinnedHttpsTransport()
                    ),
                    secret_reference=secret,
                    auth_header_name=(
                        "x-apisports-key"
                    ),
                )
            ),
            binding_store=binding_store,
            collector=(
                ProviderNetworkBindingCollector()
            ),
            clock=lambda: NOW,
            attempt_intent_store=(
                attempt_intent_store
            ),
        )
    )

    boundary = (
        certify_controlled_network_boundary(
            transport=governed,
            request_contract_registry=(
                contract_registry
            ),
            binding_store=(
                binding_store
            ),
            network_permit_store=(
                permit_store
            ),
            network_call_evidence_store=(
                call_store
            ),
        )
    )

    certification = (
        certify_provider_activation_readiness(
            network_boundary_certification=(
                boundary
            ),
            governed_transport=(
                governed
            ),
            secret_reference=secret,
            request_contract_registry=(
                contract_registry
            ),
            request_contract_ids=(),
            contract_endpoint_binding_store=(
                SQLiteProviderContractEndpointBindingStore(
                    tmp_path / "endpoint.db"
                )
            ),
            legal_evidence_store=(
                SQLiteProviderLegalEvidenceStore(
                    tmp_path / "legal.db"
                )
            ),
            rights_decision=(
                _rights_blocked()
            ),
            attempt_intent_store=(
                attempt_intent_store
            ),
        )
    )

    assert (
        certification.status
        == "NOT_READY"
    )
    assert (
        "NONEMPTY_REQUEST_CONTRACT_EVIDENCE_REQUIRED"
        in certification.blockers
    )
