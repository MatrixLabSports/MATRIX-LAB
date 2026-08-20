from __future__ import annotations

from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
    MatrixPinnedHttpsTransport,
)
from app.providers.api_football.client import ApiFootballClient


def _build_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
) -> ApiFootballClient:
    if not isinstance(pinned_transport, MatrixPinnedHttpsTransport):
        raise ValueError("PINNED_HTTPS_TRANSPORT_REQUIRED")
    governed = GovernedProviderHttpSession(
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        pinned_transport=pinned_transport,
        clock=clock,
    )
    return ApiFootballClient(config, session=governed)


def build_governed_api_football_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
) -> ApiFootballClient:
    if authority.mode != "PRODUCTION":
        raise ValueError("PRODUCTION_CLIENT_REQUIRES_PRODUCTION_MODE")
    return _build_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        pinned_transport=pinned_transport,
    )


def _build_bootstrap_api_football_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    pinned_transport: MatrixPinnedHttpsTransport,
) -> ApiFootballClient:
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError("BOOTSTRAP_CLIENT_REQUIRES_BOOTSTRAP_MODE")
    return _build_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        pinned_transport=pinned_transport,
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
    params=None,
):
    from app.core.provider_bootstrap_quarantine import execute_bootstrap_probe

    client = _build_bootstrap_api_football_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        pinned_transport=pinned_transport,
    )
    return execute_bootstrap_probe(
        authority=authority,
        client=client,
        endpoint=endpoint,
        params=params,
    )
