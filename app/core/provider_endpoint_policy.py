from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit


_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "token",
    "password",
    "secret",
    "client_secret",
}


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ProviderEndpointPolicy:
    provider_key: str
    endpoint_origin: str
    tls_required: bool
    certificate_verification_required: bool
    embedded_credentials_allowed: bool
    secret_query_parameters_allowed: bool
    policy_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-endpoint-policy/1",
            "provider_key": self.provider_key,
            "endpoint_origin": self.endpoint_origin,
            "tls_required": self.tls_required,
            "certificate_verification_required": (
                self.certificate_verification_required
            ),
            "embedded_credentials_allowed": (
                self.embedded_credentials_allowed
            ),
            "secret_query_parameters_allowed": (
                self.secret_query_parameters_allowed
            ),
            "policy_fingerprint": self.policy_fingerprint,
        }


def build_provider_endpoint_policy(
    *,
    provider_key: str,
    endpoint_url: str,
) -> ProviderEndpointPolicy:
    if (
        not isinstance(provider_key, str)
        or not provider_key
    ):
        raise ValueError("INVALID_PROVIDER_KEY")

    if (
        not isinstance(endpoint_url, str)
        or not endpoint_url
    ):
        raise ValueError("INVALID_PROVIDER_ENDPOINT")

    parsed = urlsplit(endpoint_url)

    if parsed.scheme.lower() != "https":
        raise ValueError("PROVIDER_ENDPOINT_TLS_REQUIRED")

    if not parsed.hostname:
        raise ValueError("INVALID_PROVIDER_ENDPOINT_HOST")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "EMBEDDED_PROVIDER_CREDENTIALS_FORBIDDEN"
        )

    for key, _ in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            raise ValueError(
                "SECRET_QUERY_PARAMETER_FORBIDDEN"
            )

    host = parsed.hostname.lower()

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if ip.is_loopback:
            raise ValueError(
                "LOOPBACK_PROVIDER_ENDPOINT_FORBIDDEN"
            )

    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError(
            "LOOPBACK_PROVIDER_ENDPOINT_FORBIDDEN"
        )

    port = parsed.port
    origin = (
        f"https://{host}"
        if port in {None, 443}
        else f"https://{host}:{port}"
    )

    base = {
        "schema": "matrix.provider-endpoint-policy/1",
        "provider_key": provider_key,
        "endpoint_origin": origin,
        "tls_required": True,
        "certificate_verification_required": True,
        "embedded_credentials_allowed": False,
        "secret_query_parameters_allowed": False,
    }

    return ProviderEndpointPolicy(
        provider_key=provider_key,
        endpoint_origin=origin,
        tls_required=True,
        certificate_verification_required=True,
        embedded_credentials_allowed=False,
        secret_query_parameters_allowed=False,
        policy_fingerprint=_sha(base),
    )
