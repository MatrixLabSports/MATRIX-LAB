from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import (
    parse_qsl,
    quote,
    urlencode,
    urlsplit,
    urlunsplit,
)


_SENSITIVE_NAMES = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "apikey",
    "x_api_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "x_auth_token",
    "token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "private_key",
    "cookie",
    "set_cookie",
}


def _normalized_key(value: object) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("-", "_")
    )


def _is_sensitive_key(value: object) -> bool:
    normalized = _normalized_key(value)

    return (
        normalized in _SENSITIVE_NAMES
        or normalized.endswith("_api_key")
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_private_key")
    )


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    if parsed.scheme not in {"http", "https"}:
        return value

    query_pairs = []

    for key, item in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):
        query_pairs.append(
            (
                key,
                (
                    "[REDACTED]"
                    if _is_sensitive_key(key)
                    else item
                ),
            )
        )

    query = urlencode(
        query_pairs,
        doseq=True,
        quote_via=quote,
    )

    netloc = parsed.netloc

    if parsed.username is not None:
        host = parsed.hostname or ""
        port = (
            ""
            if parsed.port is None
            else f":{parsed.port}"
        )
        netloc = f"[REDACTED]@{host}{port}"

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            query,
            parsed.fragment,
        )
    )


def _sanitize_string(value: str) -> str:
    stripped = value.lstrip()

    if (
        stripped.lower().startswith("bearer ")
        or stripped.lower().startswith("basic ")
    ):
        return "[REDACTED]"

    if value.startswith(("http://", "https://")):
        return _sanitize_url(value)

    return value


def sanitize_sensitive_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            if _is_sensitive_key(key):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = (
                    sanitize_sensitive_payload(item)
                )

        return sanitized

    if (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (str, bytes, bytearray),
        )
    ):
        return [
            sanitize_sensitive_payload(item)
            for item in value
        ]

    if isinstance(value, str):
        return _sanitize_string(value)

    return value


def assert_no_sensitive_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                _is_sensitive_key(key)
                and item != "[REDACTED]"
            ):
                raise ValueError(
                    "UNREDACTED_SENSITIVE_FIELD:"
                    f"{key}"
                )

            assert_no_sensitive_fields(item)

    elif (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (str, bytes, bytearray),
        )
    ):
        for item in value:
            assert_no_sensitive_fields(item)

    elif isinstance(value, str):
        sanitized = _sanitize_string(value)

        if sanitized != value:
            raise ValueError(
                "UNREDACTED_SENSITIVE_TEXT"
            )
