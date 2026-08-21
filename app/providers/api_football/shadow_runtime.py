from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from app.core.governed_provider_http import (
    MatrixPinnedHttpsTransport,
)
from app.core.governed_provider_request import (
    GovernedProviderRequestClient,
    JitSecretPinnedHttpsTransport,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_network_execution_authorization import (
    ProviderNetworkAuthority,
)
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
    register_api_football_contract_endpoint_bindings,
    register_api_football_request_contracts,
)


_ALLOWED_MODES = {
    "DRY_RUN",
    "SHADOW",
}


class ShadowBlockedPinnedHttpsTransport(
    MatrixPinnedHttpsTransport
):
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True

    def get_pinned(
        self,
        **kwargs: Any,
    ):
        raise ValueError(
            "SHADOW_NETWORK_EXECUTION_FORBIDDEN"
        )


class ShadowNoNetworkSession:
    def __init__(
        self,
        *,
        governed_transport: (
            BindingAuditPinnedHttpsTransport
        ),
        authority_type,
    ) -> None:
        self.governed_transport = (
            governed_transport
        )
        self.authority_type = authority_type
        self.calls: list[
            Mapping[str, Any]
        ] = []

    def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        record = {
            "url": url,
            "kwargs": dict(
                kwargs
            ),
            "network_call_performed": False,
            "secret_resolved": False,
            "network_permit_issued": False,
        }

        self.calls.append(
            record
        )

        return record


@dataclass(frozen=True)
class ApiFootballShadowReadiness:
    mode: str
    contract_count: int
    endpoint_binding_count: int
    rights_authorized: bool
    governed_request_client_verified: bool
    governed_transport_topology_verified: bool
    network_authority_type_verified: bool
    external_network_allowed: bool
    real_provider_execution_authorized: bool
    blockers: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-shadow-readiness/2"
            ),
            "mode": self.mode,
            "contract_count": self.contract_count,
            "endpoint_binding_count": (
                self.endpoint_binding_count
            ),
            "rights_authorized": (
                self.rights_authorized
            ),
            "governed_request_client_verified": (
                self.governed_request_client_verified
            ),
            "governed_transport_topology_verified": (
                self.governed_transport_topology_verified
            ),
            "network_authority_type_verified": (
                self.network_authority_type_verified
            ),
            "external_network_allowed": False,
            "real_provider_execution_authorized": False,
            "blockers": list(
                self.blockers
            ),
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class ApiFootballShadowRequest:
    mode: str
    contract_name: str
    contract_id: str
    endpoint_manifest_id: str
    authorization_fingerprint: str
    path: str
    parameter_names: tuple[str, ...]
    parameter_values_fingerprint: str
    governed_request_client_used: bool
    governed_transport_topology_verified: bool
    network_call_performed: bool
    network_permit_issued: bool
    secret_resolved: bool
    real_provider_execution_authorized: bool

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-shadow-request/2"
            ),
            "mode": self.mode,
            "contract_name": self.contract_name,
            "contract_id": self.contract_id,
            "endpoint_manifest_id": (
                self.endpoint_manifest_id
            ),
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
            "governed_request_client_used": True,
            "governed_transport_topology_verified": True,
            "network_call_performed": False,
            "network_permit_issued": False,
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
        base_url: str,
        registry: (
            SQLiteProviderRequestContractRegistry
        ),
        contract_endpoint_binding_store: (
            SQLiteProviderContractEndpointBindingStore
        ),
        endpoint_manifest_ids: Mapping[
            str,
            str,
        ],
        binding_store: (
            SQLiteProviderNetworkBindingEvidenceStore
        ),
        attempt_intent_store: (
            SQLiteProviderAttemptIntentStore
        ),
        secret_reference: SecretReference,
        clock: Callable[
            [],
            datetime,
        ],
        valid_from: datetime,
        valid_until: datetime | None = None,
        rights_decision: (
            ProviderRightsDecision
            | None
        ) = None,
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

        self.endpoint_bindings = (
            register_api_football_contract_endpoint_bindings(
                contracts=self.contracts,
                endpoint_manifest_ids=(
                    endpoint_manifest_ids
                ),
                registry=(
                    contract_endpoint_binding_store
                ),
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )

        self.contract_endpoint_binding_store = (
            contract_endpoint_binding_store
        )

        blocked_transport = (
            ShadowBlockedPinnedHttpsTransport()
        )

        jit_transport = (
            JitSecretPinnedHttpsTransport(
                inner=blocked_transport,
                secret_reference=(
                    secret_reference
                ),
                auth_header_name=(
                    "x-apisports-key"
                ),
                resolver=lambda reference: (
                    (_ for _ in ()).throw(
                        ValueError(
                            "SHADOW_SECRET_RESOLUTION_FORBIDDEN"
                        )
                    )
                ),
            )
        )

        governed_transport = (
            BindingAuditPinnedHttpsTransport(
                inner=jit_transport,
                binding_store=(
                    binding_store
                ),
                collector=(
                    ProviderNetworkBindingCollector()
                ),
                clock=clock,
                attempt_intent_store=(
                    attempt_intent_store
                ),
            )
        )

        self.shadow_session = (
            ShadowNoNetworkSession(
                governed_transport=(
                    governed_transport
                ),
                authority_type=(
                    ProviderNetworkAuthority
                ),
            )
        )

        self.request_client = (
            GovernedProviderRequestClient(
                provider_key=(
                    "api_football"
                ),
                sport="football",
                base_url=base_url,
                timeout_seconds=5.0,
                secret_reference=(
                    secret_reference
                ),
                request_contract_registry=(
                    registry
                ),
                governed_session=(
                    self.shadow_session
                ),
                clock=clock,
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

        topology_verified = (
            isinstance(
                self.request_client,
                GovernedProviderRequestClient,
            )
            and isinstance(
                governed_transport,
                BindingAuditPinnedHttpsTransport,
            )
            and isinstance(
                governed_transport.inner,
                JitSecretPinnedHttpsTransport,
            )
            and isinstance(
                governed_transport.inner.inner,
                ShadowBlockedPinnedHttpsTransport,
            )
        )

        self.readiness = (
            ApiFootballShadowReadiness(
                mode=mode,
                contract_count=len(
                    self.contracts
                ),
                endpoint_binding_count=len(
                    self.endpoint_bindings
                ),
                rights_authorized=(
                    rights_authorized
                ),
                governed_request_client_verified=True,
                governed_transport_topology_verified=(
                    topology_verified
                ),
                network_authority_type_verified=(
                    self.shadow_session.authority_type
                    is ProviderNetworkAuthority
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

        endpoint_binding = (
            self.endpoint_bindings[
                contract_name
            ]
        )

        self.contract_endpoint_binding_store.authorize(
            request_contract_id=(
                contract.contract_id
            ),
            endpoint_manifest_id=(
                endpoint_binding.endpoint_manifest_id
            ),
            path=contract.path,
            now=self.clock(),
        )

        result = self.request_client.get(
            path=contract.path,
            request_contract_id=(
                contract.contract_id
            ),
            params=params,
        )

        kwargs = result[
            "kwargs"
        ]

        return ApiFootballShadowRequest(
            mode=self.mode,
            contract_name=(
                contract_name
            ),
            contract_id=(
                contract.contract_id
            ),
            endpoint_manifest_id=(
                endpoint_binding.endpoint_manifest_id
            ),
            authorization_fingerprint=(
                kwargs[
                    "matrix_request_contract_fingerprint"
                ]
            ),
            path=contract.path,
            parameter_names=tuple(
                kwargs[
                    "matrix_request_parameter_names"
                ]
            ),
            parameter_values_fingerprint=(
                kwargs[
                    "matrix_request_parameter_values_fingerprint"
                ]
            ),
            governed_request_client_used=True,
            governed_transport_topology_verified=(
                self.readiness.governed_transport_topology_verified
            ),
            network_call_performed=False,
            network_permit_issued=False,
            secret_resolved=False,
            real_provider_execution_authorized=False,
        )
