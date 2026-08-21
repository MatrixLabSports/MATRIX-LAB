from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.provider_rights_authorization import (
    ProviderRightsDecision,
)
from app.core.secret_reference import (
    SecretReference,
)
from app.providers.api_football.request_contracts import (
    register_api_football_request_contracts,
)


_ALLOWED_MODES = {
    "DRY_RUN",
    "SHADOW",
}


@dataclass(frozen=True)
class ApiFootballShadowReadiness:
    mode: str
    contract_count: int
    rights_authorized: bool
    external_network_allowed: bool
    real_provider_execution_authorized: bool
    blockers: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-shadow-readiness/1"
            ),
            "mode": self.mode,
            "contract_count": self.contract_count,
            "rights_authorized": (
                self.rights_authorized
            ),
            "external_network_allowed": False,
            "real_provider_execution_authorized": False,
            "blockers": list(self.blockers),
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class ApiFootballShadowRequest:
    mode: str
    contract_name: str
    contract_id: str
    authorization_fingerprint: str
    path: str
    parameter_names: tuple[str, ...]
    parameter_values_fingerprint: str
    network_call_performed: bool
    secret_resolved: bool
    real_provider_execution_authorized: bool

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-shadow-request/1"
            ),
            "mode": self.mode,
            "contract_name": self.contract_name,
            "contract_id": self.contract_id,
            "authorization_fingerprint": (
                self.authorization_fingerprint
            ),
            "path": self.path,
            "parameter_names": list(
                self.parameter_names
            ),
            "parameter_values_fingerprint": (
                self.parameter_values_fingerprint
            ),
            "network_call_performed": False,
            "secret_resolved": False,
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


class ApiFootballShadowRuntime:
    def __init__(
        self,
        *,
        mode: str,
        registry: SQLiteProviderRequestContractRegistry,
        secret_reference: SecretReference,
        clock: Callable[[], datetime],
        valid_from: datetime,
        valid_until: datetime | None = None,
        rights_decision: ProviderRightsDecision | None = None,
    ) -> None:
        if mode not in _ALLOWED_MODES:
            raise ValueError(
                "INVALID_SHADOW_RUNTIME_MODE"
            )

        if (
            secret_reference.provider_key
            != "api_football"
        ):
            raise ValueError(
                "API_FOOTBALL_SECRET_REFERENCE_REQUIRED"
            )

        self.mode = mode
        self.registry = registry
        self.secret_reference = (
            secret_reference
        )
        self.clock = clock

        self.contracts = (
            register_api_football_request_contracts(
                registry=registry,
                secret_reference_fingerprint=(
                    secret_reference.reference_fingerprint
                ),
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )

        rights_authorized = (
            rights_decision is not None
            and rights_decision.authorized
        )

        blockers: list[str] = []

        if not rights_authorized:
            blockers.append(
                "PROVIDER_RIGHTS_NOT_AUTHORIZED"
            )

        blockers.append(
            "REAL_PROVIDER_EXECUTION_DISABLED"
        )

        self.readiness = (
            ApiFootballShadowReadiness(
                mode=mode,
                contract_count=len(
                    self.contracts
                ),
                rights_authorized=(
                    rights_authorized
                ),
                external_network_allowed=False,
                real_provider_execution_authorized=False,
                blockers=tuple(
                    blockers
                ),
            )
        )

    def preview(
        self,
        *,
        contract_name: str,
        params: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> ApiFootballShadowRequest:
        contract = self.contracts.get(
            contract_name
        )

        if contract is None:
            raise ValueError(
                "UNKNOWN_API_FOOTBALL_CONTRACT"
            )

        authorization = (
            self.registry.authorize(
                contract_id=(
                    contract.contract_id
                ),
                provider_key=(
                    "api_football"
                ),
                sport="football",
                method="GET",
                path=contract.path,
                params=params,
                secret_reference_fingerprint=(
                    self.secret_reference.reference_fingerprint
                ),
                now=self.clock(),
            )
        )

        return ApiFootballShadowRequest(
            mode=self.mode,
            contract_name=(
                contract_name
            ),
            contract_id=(
                contract.contract_id
            ),
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            path=contract.path,
            parameter_names=(
                authorization.parameter_names
            ),
            parameter_values_fingerprint=(
                authorization.parameter_values_fingerprint
            ),
            network_call_performed=False,
            secret_resolved=False,
            real_provider_execution_authorized=False,
        )
