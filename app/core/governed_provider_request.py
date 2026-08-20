from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
    MatrixPinnedHttpsTransport,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    SecretReference,
    resolve_secret_runtime,
)


class JitSecretPinnedHttpsTransport(MatrixPinnedHttpsTransport):
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True

    def __init__(
        self,
        *,
        inner: MatrixPinnedHttpsTransport,
        secret_reference: SecretReference,
        auth_header_name: str,
        resolver: Callable[
            [SecretReference],
            str,
        ] = resolve_secret_runtime,
    ) -> None:
        if not isinstance(inner, MatrixPinnedHttpsTransport):
            raise ValueError("PINNED_HTTPS_TRANSPORT_REQUIRED")

        if (
            not auth_header_name
            or "\r" in auth_header_name
            or "\n" in auth_header_name
        ):
            raise ValueError("INVALID_AUTH_HEADER_NAME")

        self.inner = inner
        self.secret_reference = secret_reference
        self.auth_header_name = auth_header_name
        self.resolver = resolver

    def get_pinned(
        self,
        *,
        url: str,
        original_host: str,
        resolved_ips: tuple[str, ...],
        allow_redirects: bool,
        verify: bool,
        **kwargs: Any,
    ):
        expected_fp = kwargs.pop(
            "matrix_request_secret_reference_fingerprint",
            None,
        )

        if (
            expected_fp
            != self.secret_reference.reference_fingerprint
        ):
            raise ValueError("REQUEST_SECRET_REFERENCE_MISMATCH")

        headers = dict(
            kwargs.pop("headers", {})
        )

        if any(
            str(key).lower()
            == self.auth_header_name.lower()
            for key in headers
        ):
            raise ValueError("CALLER_SECRET_HEADER_FORBIDDEN")

        secret_value = self.resolver(
            self.secret_reference
        )

        try:
            headers[
                self.auth_header_name
            ] = secret_value

            return self.inner.get_pinned(
                url=url,
                original_host=original_host,
                resolved_ips=resolved_ips,
                allow_redirects=allow_redirects,
                verify=verify,
                headers=headers,
                **kwargs,
            )
        finally:
            headers.pop(
                self.auth_header_name,
                None,
            )
            secret_value = None


@dataclass(frozen=True)
class GovernedProviderRequestClient:
    provider_key: str
    sport: str
    base_url: str
    timeout_seconds: float
    secret_reference: SecretReference
    request_contract_registry: SQLiteProviderRequestContractRegistry
    governed_session: GovernedProviderHttpSession
    clock: Callable[[], datetime]

    def get(
        self,
        *,
        path: str,
        request_contract_id: str,
        params: Mapping[str, Any] | None = None,
    ):
        if (
            self.secret_reference.provider_key
            != self.provider_key
        ):
            raise ValueError("SECRET_PROVIDER_BINDING_MISMATCH")

        parsed = urlsplit(self.base_url)

        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("INVALID_GOVERNED_PROVIDER_BASE_URL")

        if (
            not path.startswith("/")
            or "?" in path
            or "#" in path
        ):
            raise ValueError("INVALID_GOVERNED_REQUEST_PATH")

        decision = self.request_contract_registry.authorize(
            contract_id=request_contract_id,
            provider_key=self.provider_key,
            sport=self.sport,
            method="GET",
            path=path,
            params=params,
            secret_reference_fingerprint=(
                self.secret_reference.reference_fingerprint
            ),
            now=self.clock(),
        )

        return self.governed_session.get(
            self.base_url.rstrip("/") + path,
            params=None if params is None else dict(params),
            timeout=self.timeout_seconds,
            matrix_request_contract_fingerprint=(
                decision.authorization_fingerprint
            ),
            matrix_request_secret_reference_fingerprint=(
                decision.secret_reference_fingerprint
            ),
        )
