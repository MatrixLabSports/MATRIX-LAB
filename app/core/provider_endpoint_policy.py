from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import posixpath
from typing import Any, Mapping
from urllib.parse import (
    parse_qsl,
    quote,
    urlencode,
    urlsplit,
)


_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "x_api_key",
    "access_token",
    "auth_token",
    "x_auth_token",
    "token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "authorization",
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


def _normalized_key(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
    )


def _is_sensitive_query_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return (
        normalized in _SENSITIVE_QUERY_KEYS
        or normalized.endswith("_api_key")
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
    )


@dataclass(frozen=True)
class ProviderEndpointPolicy:
    provider_key: str
    endpoint_origin: str
    endpoint_target: str
    endpoint_target_fingerprint: str
    tls_required: bool
    certificate_verification_required: bool
    embedded_credentials_allowed: bool
    secret_query_parameters_allowed: bool
    non_global_ip_literals_allowed: bool
    fragments_allowed: bool
    policy_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-endpoint-policy/2",
            "provider_key": self.provider_key,
            "endpoint_origin": self.endpoint_origin,
            "endpoint_target": self.endpoint_target,
            "endpoint_target_fingerprint": (
                self.endpoint_target_fingerprint
            ),
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
            "non_global_ip_literals_allowed": (
                self.non_global_ip_literals_allowed
            ),
            "fragments_allowed": self.fragments_allowed,
            "policy_fingerprint": self.policy_fingerprint,
        }


def build_provider_endpoint_policy(
    *,
    provider_key: str,
    endpoint_url: str,
) -> ProviderEndpointPolicy:
    if not isinstance(provider_key, str) or not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")

    if not isinstance(endpoint_url, str) or not endpoint_url:
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

    if parsed.fragment:
        raise ValueError(
            "PROVIDER_ENDPOINT_FRAGMENT_FORBIDDEN"
        )

    host = parsed.hostname.lower()

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host in {"localhost", "localhost.localdomain"}:
            raise ValueError(
                "LOOPBACK_PROVIDER_ENDPOINT_FORBIDDEN"
            )
    else:
        if not ip.is_global:
            raise ValueError(
                "NON_GLOBAL_PROVIDER_IP_FORBIDDEN"
            )

    path = parsed.path or "/"

    if ".." in path.split("/"):
        raise ValueError(
            "PROVIDER_ENDPOINT_PATH_TRAVERSAL_FORBIDDEN"
        )

    normalized_path = posixpath.normpath(path)

    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path

    query_pairs = parse_qsl(
        parsed.query,
        keep_blank_values=True,
    )

    for key, _ in query_pairs:
        if _is_sensitive_query_key(key):
            raise ValueError(
                "SECRET_QUERY_PARAMETER_FORBIDDEN"
            )

    normalized_query = urlencode(
        sorted(query_pairs),
        doseq=True,
        quote_via=quote,
    )

    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(
            "INVALID_PROVIDER_ENDPOINT_PORT"
        ) from error

    origin = (
        f"https://{host}"
        if port in {None, 443}
        else f"https://{host}:{port}"
    )

    endpoint_target = (
        origin
        + normalized_path
        + (
            ""
            if not normalized_query
            else "?" + normalized_query
        )
    )

    endpoint_target_fingerprint = _sha(
        {
            "schema": "matrix.provider-endpoint-target/1",
            "provider_key": provider_key,
            "endpoint_target": endpoint_target,
        }
    )

    base = {
        "schema": "matrix.provider-endpoint-policy/2",
        "provider_key": provider_key,
        "endpoint_origin": origin,
        "endpoint_target": endpoint_target,
        "endpoint_target_fingerprint": (
            endpoint_target_fingerprint
        ),
        "tls_required": True,
        "certificate_verification_required": True,
        "embedded_credentials_allowed": False,
        "secret_query_parameters_allowed": False,
        "non_global_ip_literals_allowed": False,
        "fragments_allowed": False,
    }

    return ProviderEndpointPolicy(
        provider_key=provider_key,
        endpoint_origin=origin,
        endpoint_target=endpoint_target,
        endpoint_target_fingerprint=(
            endpoint_target_fingerprint
        ),
        tls_required=True,
        certificate_verification_required=True,
        embedded_credentials_allowed=False,
        secret_query_parameters_allowed=False,
        non_global_ip_literals_allowed=False,
        fragments_allowed=False,
        policy_fingerprint=_sha(base),
    )
