from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
import re
from typing import Any, Mapping


_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_SECRET_TYPES = {
    "API_KEY",
    "TOKEN",
    "PASSWORD",
    "CLIENT_SECRET",
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
class SecretReference:
    provider_key: str
    environment_variable: str
    secret_type: str
    reference_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.secret-reference/1",
            "provider_key": self.provider_key,
            "environment_variable": (
                self.environment_variable
            ),
            "secret_type": self.secret_type,
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "reference_fingerprint": (
                self.reference_fingerprint
            ),
        }


def build_secret_reference(
    *,
    provider_key: str,
    environment_variable: str,
    secret_type: str,
) -> SecretReference:
    if (
        not isinstance(provider_key, str)
        or not provider_key
    ):
        raise ValueError("INVALID_PROVIDER_KEY")

    if (
        not isinstance(environment_variable, str)
        or not _ENV_RE.fullmatch(
            environment_variable
        )
    ):
        raise ValueError(
            "INVALID_SECRET_ENVIRONMENT_VARIABLE"
        )

    if secret_type not in _SECRET_TYPES:
        raise ValueError("INVALID_SECRET_TYPE")

    base = {
        "schema": "matrix.secret-reference/1",
        "provider_key": provider_key,
        "environment_variable": environment_variable,
        "secret_type": secret_type,
        "raw_secret_persisted": False,
        "raw_secret_logged": False,
    }

    return SecretReference(
        provider_key=provider_key,
        environment_variable=environment_variable,
        secret_type=secret_type,
        reference_fingerprint=_sha(base),
    )


def resolve_secret_runtime(
    reference: SecretReference,
) -> str:
    expected = build_secret_reference(
        provider_key=reference.provider_key,
        environment_variable=(
            reference.environment_variable
        ),
        secret_type=reference.secret_type,
    )

    if expected != reference:
        raise ValueError(
            "SECRET_REFERENCE_DERIVATION_MISMATCH"
        )

    value = os.environ.get(
        reference.environment_variable
    )

    if value is None or not value:
        raise ValueError("SECRET_NOT_AVAILABLE")

    if "\n" in value or "\r" in value:
        raise ValueError("INVALID_SECRET_VALUE")

    return value
