from __future__ import annotations

from typing import Any
import requests

from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
)
from app.providers.api_football.client import (
    ApiFootballClient,
)


def _build_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    underlying_session: Any | None,
) -> ApiFootballClient:
    session = underlying_session or requests.Session()
    governed = GovernedProviderHttpSession(
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        underlying_session=session,
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
    underlying_session: Any | None = None,
) -> ApiFootballClient:
    if authority.mode != "PRODUCTION":
        raise ValueError("PRODUCTION_CLIENT_REQUIRES_PRODUCTION_MODE")
    return _build_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        underlying_session=underlying_session,
    )


def _build_bootstrap_api_football_client(
    *,
    config,
    authority,
    network_permit_store,
    call_evidence_store,
    clock,
    underlying_session: Any | None = None,
) -> ApiFootballClient:
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError("BOOTSTRAP_CLIENT_REQUIRES_BOOTSTRAP_MODE")
    return _build_client(
        config=config,
        authority=authority,
        network_permit_store=network_permit_store,
        call_evidence_store=call_evidence_store,
        clock=clock,
        underlying_session=underlying_session,
    )
