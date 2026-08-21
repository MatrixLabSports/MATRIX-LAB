from __future__ import annotations

from app.core.controlled_network_certification import (
    NetworkBoundaryCertification,
    require_real_provider_execution_authorized,
)
from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    require_provider_activation_authorized,
)
from app.core.provider_activation_rehearsal import (
    ProviderActivationRehearsalCertification,
    require_activation_rehearsal_for_real_execution,
)
from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
    MatrixPinnedHttpsTransport,
)
from app.core.governed_provider_request import (
    GovernedProviderRequestClient,
    JitSecretPinnedHttpsTransport,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.secret_reference import SecretReference


def _build_controlled_request_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
    request_contract_registry: SQLiteProviderRequestContractRegistry,
    secret_reference: SecretReference,
    binding_store: SQLiteProviderNetworkBindingEvidenceStore,
    binding_collector: ProviderNetworkBindingCollector,
    attempt_intent_store: SQLiteProviderAttemptIntentStore,
) -> GovernedProviderRequestClient:
    if not isinstance(pinned_transport, MatrixPinnedHttpsTransport):
        raise ValueError("PINNED_HTTPS_TRANSPORT_REQUIRED")
    if not isinstance(
        request_contract_registry,
        SQLiteProviderRequestContractRegistry,
    ):
        raise ValueError("REQUEST_CONTRACT_REGISTRY_REQUIRED")
    if not isinstance(secret_reference, SecretReference):
        raise ValueError("SECRET_REFERENCE_REQUIRED")
    if secret_reference.provider_key != "api_football":
        raise ValueError("API_FOOTBALL_SECRET_REFERENCE_REQUIRED")
    if not isinstance(
        binding_store,
        SQLiteProviderNetworkBindingEvidenceStore,
    ):
        raise ValueError("NETWORK_BINDING_STORE_REQUIRED")
    if not isinstance(
        binding_collector,
        ProviderNetworkBindingCollector,
    ):
        raise ValueError("NETWORK_BINDING_COLLECTOR_REQUIRED")
    if not isinstance(
        attempt_intent_store,
        SQLiteProviderAttemptIntentStore,
    ):
        raise ValueError("ATTEMPT_INTENT_STORE_REQUIRED")

    jit_transport = JitSecretPinnedHttpsTransport(
        inner=pinned_transport,
        secret_reference=secret_reference,
        auth_header_name="x-apisports-key",
    )
    bound_transport = BindingAuditPinnedHttpsTransport(
        inner=jit_transport,
        binding_store=binding_store,
        collector=binding_collector,
        clock=clock,
        attempt_intent_store=(
            attempt_intent_store
        ),
    )
    governed_session = GovernedProviderHttpSession(
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        pinned_transport=bound_transport,
        clock=clock,
    )

    return GovernedProviderRequestClient(
        provider_key="api_football",
        sport="football",
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        secret_reference=secret_reference,
        request_contract_registry=request_contract_registry,
        governed_session=governed_session,
        clock=clock,
    )


def build_governed_api_football_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
    network_certification: NetworkBoundaryCertification | None = None,
    activation_readiness_certification: (
        ProviderActivationReadinessCertification
        | None
    ) = None,
    activation_rehearsal_certification: (
        ProviderActivationRehearsalCertification
        | None
    ) = None,
    request_contract_registry=None,
    secret_reference=None,
    binding_store=None,
    binding_collector=None,
    attempt_intent_store=None,
) -> GovernedProviderRequestClient:
    if authority.mode != "PRODUCTION":
        raise ValueError("PRODUCTION_CLIENT_REQUIRES_PRODUCTION_MODE")

    require_real_provider_execution_authorized(
        network_certification
    )

    if (
        activation_readiness_certification
        is None
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_READINESS_REQUIRED"
        )

    if (
        activation_rehearsal_certification
        is None
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_REHEARSAL_REQUIRED"
        )

    require_provider_activation_authorized(
        activation_readiness_certification
    )
    require_activation_rehearsal_for_real_execution(
        activation_rehearsal_certification
    )

    return _build_controlled_request_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        pinned_transport=pinned_transport,
        request_contract_registry=request_contract_registry,
        secret_reference=secret_reference,
        binding_store=binding_store,
        binding_collector=binding_collector,
        attempt_intent_store=(
            attempt_intent_store
        ),
    )


def _build_bootstrap_api_football_client(
    **kwargs,
):
    from app.providers.api_football.bootstrap_client import (
        build_bootstrap_api_football_client,
    )
    return build_bootstrap_api_football_client(
        **kwargs,
    )


def execute_governed_api_football_bootstrap_probe(
    **kwargs,
):
    from app.providers.api_football.bootstrap_client import (
        execute_governed_api_football_bootstrap_probe
        as execute_bootstrap,
    )
    return execute_bootstrap(
        **kwargs,
    )
