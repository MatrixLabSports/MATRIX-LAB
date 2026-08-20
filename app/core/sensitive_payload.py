from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_SENSITIVE_NAMES = {
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
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


def sanitize_sensitive_payload(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            normalized = _normalized_key(
                key
            )

            if normalized in _SENSITIVE_NAMES:
                sanitized[str(key)] = (
                    "[REDACTED]"
                )
            else:
                sanitized[str(key)] = (
                    sanitize_sensitive_payload(
                        item
                    )
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
            sanitize_sensitive_payload(
                item
            )
            for item in value
        ]

    return value


def assert_no_sensitive_fields(
    value: Any,
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized_key(
                key
            )

            if (
                normalized
                in _SENSITIVE_NAMES
                and item != "[REDACTED]"
            ):
                raise ValueError(
                    "UNREDACTED_SENSITIVE_FIELD:"
                    f"{key}"
                )

            assert_no_sensitive_fields(
                item
            )

    elif (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (str, bytes, bytearray),
        )
    ):
        for item in value:
            assert_no_sensitive_fields(
                item
            )
