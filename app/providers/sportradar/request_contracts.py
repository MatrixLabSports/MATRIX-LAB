from __future__ import annotations

from datetime import datetime
from typing import Mapping

from app.core.provider_request_contract import (
    ProviderRequestContract,
    SQLiteProviderRequestContractRegistry,
    build_provider_request_contract,
)
from app.providers.sportradar.config import SportradarConfig
from app.providers.sportradar.dynamic_paths import (
    build_sportradar_dynamic_path,
    sportradar_dynamic_parameter_rules,
)


SPORTRADAR_PROVIDER_KEY = "sportradar"
SPORTRADAR_AUTH_HEADER = "x-api-key"
SPORTRADAR_CONTRACT_SET_VERSION = "2026-09-03.v3"


def _build(
    *,
    sport: str,
    path: str,
    parameter_rules,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None,
) -> ProviderRequestContract:
    return build_provider_request_contract(
        provider_key=SPORTRADAR_PROVIDER_KEY,
        sport=sport,
        method="GET",
        path=path,
        parameter_rules=parameter_rules,
        auth_header_name=SPORTRADAR_AUTH_HEADER,
        secret_reference_fingerprint=secret_reference_fingerprint,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def build_sportradar_request_contracts(
    *,
    config: SportradarConfig,
    sport: str,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> Mapping[str, ProviderRequestContract]:
    if sport not in {"tennis", "football"}:
        raise ValueError("INVALID_SPORTRADAR_SPORT")

    specifications = {
        "competitions": config.static_path(sport=sport, feed="competitions"),
        "seasons": config.static_path(sport=sport, feed="seasons"),
        "live_schedule": config.static_path(sport=sport, feed="live_schedule"),
    }

    return {
        name: _build(
            sport=sport,
            path=path,
            parameter_rules=(),
            secret_reference_fingerprint=secret_reference_fingerprint,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        for name, path in specifications.items()
    }


def build_sportradar_concrete_dynamic_contract(
    *,
    config: SportradarConfig,
    sport: str,
    feed: str,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
    resource_id: str | None = None,
    date: str | None = None,
) -> ProviderRequestContract:
    # Critical design choice: MATRIX core remains exact-path fail-closed.
    # We validate the resource/date first, derive one concrete immutable path,
    # and then register a normal exact ProviderRequestContract. No wildcard,
    # regex, prefix, or caller-controlled path authorization is introduced.
    path = build_sportradar_dynamic_path(
        config=config,
        sport=sport,
        feed=feed,
        resource_id=resource_id,
        date=date,
    )
    return _build(
        sport=sport,
        path=path,
        parameter_rules=sportradar_dynamic_parameter_rules(
            sport=sport,
            feed=feed,
        ),
        secret_reference_fingerprint=secret_reference_fingerprint,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def register_sportradar_request_contracts(
    *,
    registry: SQLiteProviderRequestContractRegistry,
    config: SportradarConfig,
    sport: str,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> Mapping[str, ProviderRequestContract]:
    contracts = build_sportradar_request_contracts(
        config=config,
        sport=sport,
        secret_reference_fingerprint=secret_reference_fingerprint,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    for contract in contracts.values():
        registry.register(contract)
    return contracts


def register_sportradar_concrete_dynamic_contract(
    *,
    registry: SQLiteProviderRequestContractRegistry,
    **kwargs,
) -> ProviderRequestContract:
    contract = build_sportradar_concrete_dynamic_contract(**kwargs)
    registry.register(contract)
    return contract
