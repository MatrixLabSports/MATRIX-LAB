from __future__ import annotations

from app.core.governed_provider_http import MatrixPinnedHttpsTransport


def build_bootstrap_api_football_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
    request_contract_registry,
    secret_reference,
    binding_store,
    binding_collector,
    attempt_intent_store,
):
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError(
            "BOOTSTRAP_CLIENT_REQUIRES_BOOTSTRAP_MODE"
        )

    from app.providers.api_football.governed_client import (
        _build_controlled_request_client,
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
        attempt_intent_store=attempt_intent_store,
    )


def execute_governed_api_football_bootstrap_probe(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    endpoint: str,
    pinned_transport: MatrixPinnedHttpsTransport,
    request_contract_registry,
    secret_reference,
    binding_store,
    binding_collector,
    attempt_intent_store,
    request_contract_id: str,
    contract_endpoint_binding_store,
    endpoint_manifest_id: str,
    params=None,
):
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError(
            "BOOTSTRAP_CLIENT_REQUIRES_BOOTSTRAP_MODE"
        )

    if endpoint != "/status":
        raise ValueError(
            "BOOTSTRAP_STATUS_ENDPOINT_REQUIRED"
        )
    if params not in (None, {}):
        raise ValueError(
            "BOOTSTRAP_STATUS_PARAMS_FORBIDDEN"
        )

    authorize_binding = getattr(
        contract_endpoint_binding_store,
        "authorize",
        None,
    )
    if not callable(authorize_binding):
        raise ValueError(
            "CONTRACT_ENDPOINT_BINDING_STORE_REQUIRED"
        )

    authorize_binding(
        request_contract_id=request_contract_id,
        endpoint_manifest_id=endpoint_manifest_id,
        path=endpoint,
        now=clock(),
    )

    client = build_bootstrap_api_football_client(
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
        attempt_intent_store=attempt_intent_store,
    )

    from app.core.provider_bootstrap_quarantine import (
        execute_bootstrap_probe,
    )

    return execute_bootstrap_probe(
        authority=authority,
        client=client,
        endpoint=endpoint,
        request_contract_id=request_contract_id,
        params=None,
    )
