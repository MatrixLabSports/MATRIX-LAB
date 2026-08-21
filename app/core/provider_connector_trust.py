from __future__ import annotations

from dataclasses import dataclass
import http.client
import socket
import ssl
from typing import Any, Mapping

from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)


@dataclass(frozen=True)
class ProviderConnectorTrustDecision:
    trusted_for_production: bool
    stdlib_pinned_transport: bool
    default_connector: bool
    default_tls_context_factory: bool
    default_response_factory: bool
    dns_pinning_capable: bool
    environment_proxy_disabled: bool
    tls_verification_required: bool
    redirects_disabled: bool
    minimum_tls_version: str | None
    blockers: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-connector-trust-decision/1"
            ),
            "trusted_for_production": (
                self.trusted_for_production
            ),
            "stdlib_pinned_transport": (
                self.stdlib_pinned_transport
            ),
            "default_connector": (
                self.default_connector
            ),
            "default_tls_context_factory": (
                self.default_tls_context_factory
            ),
            "default_response_factory": (
                self.default_response_factory
            ),
            "dns_pinning_capable": (
                self.dns_pinning_capable
            ),
            "environment_proxy_disabled": (
                self.environment_proxy_disabled
            ),
            "tls_verification_required": (
                self.tls_verification_required
            ),
            "redirects_disabled": (
                self.redirects_disabled
            ),
            "minimum_tls_version": (
                self.minimum_tls_version
            ),
            "blockers": list(
                self.blockers
            ),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def assess_pinned_transport_connector_trust(
    transport,
) -> ProviderConnectorTrustDecision:
    is_stdlib = isinstance(
        transport,
        StdlibPinnedHttpsTransport,
    )

    default_connector = (
        is_stdlib
        and getattr(
            transport,
            "_connector",
            None,
        )
        is socket.create_connection
    )

    default_context = (
        is_stdlib
        and getattr(
            transport,
            "_context_factory",
            None,
        )
        is ssl.create_default_context
    )

    default_response = (
        is_stdlib
        and getattr(
            transport,
            "_response_factory",
            None,
        )
        is http.client.HTTPResponse
    )

    dns_pinning = bool(
        getattr(
            transport,
            "matrix_dns_pinning_capable",
            False,
        )
    )

    proxy_disabled = bool(
        getattr(
            transport,
            "matrix_environment_proxy_disabled",
            False,
        )
    )

    tls_required = bool(
        getattr(
            transport,
            "matrix_tls_verification_required",
            False,
        )
    )

    redirects_disabled = bool(
        getattr(
            transport,
            "matrix_redirects_disabled",
            False,
        )
    )

    minimum_tls_version = getattr(
        transport,
        "matrix_minimum_tls_version",
        None,
    )

    blockers: list[
        str
    ] = []

    checks = (
        (
            is_stdlib,
            "STDLIB_PINNED_TRANSPORT_REQUIRED",
        ),
        (
            default_connector,
            "DEFAULT_SOCKET_CONNECTOR_REQUIRED",
        ),
        (
            default_context,
            "DEFAULT_TLS_CONTEXT_FACTORY_REQUIRED",
        ),
        (
            default_response,
            "DEFAULT_HTTP_RESPONSE_FACTORY_REQUIRED",
        ),
        (
            dns_pinning,
            "DNS_PINNING_CAPABILITY_REQUIRED",
        ),
        (
            proxy_disabled,
            "ENVIRONMENT_PROXY_MUST_REMAIN_DISABLED",
        ),
        (
            tls_required,
            "TLS_VERIFICATION_MUST_REMAIN_REQUIRED",
        ),
        (
            redirects_disabled,
            "REDIRECTS_MUST_REMAIN_DISABLED",
        ),
        (
            minimum_tls_version
            == "TLSv1_2",
            "TLS12_MINIMUM_REQUIRED",
        ),
    )

    for ok, reason in checks:
        if not ok:
            blockers.append(
                reason
            )

    return ProviderConnectorTrustDecision(
        trusted_for_production=(
            not blockers
        ),
        stdlib_pinned_transport=(
            is_stdlib
        ),
        default_connector=(
            default_connector
        ),
        default_tls_context_factory=(
            default_context
        ),
        default_response_factory=(
            default_response
        ),
        dns_pinning_capable=(
            dns_pinning
        ),
        environment_proxy_disabled=(
            proxy_disabled
        ),
        tls_verification_required=(
            tls_required
        ),
        redirects_disabled=(
            redirects_disabled
        ),
        minimum_tls_version=(
            minimum_tls_version
        ),
        blockers=tuple(
            blockers
        ),
    )


def require_trusted_production_connector(
    transport,
) -> ProviderConnectorTrustDecision:
    decision = (
        assess_pinned_transport_connector_trust(
            transport
        )
    )

    if not decision.trusted_for_production:
        raise ValueError(
            "UNTRUSTED_PRODUCTION_CONNECTOR:"
            + ",".join(
                decision.blockers
            )
        )

    return decision
