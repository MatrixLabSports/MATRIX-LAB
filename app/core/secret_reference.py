from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
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


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class SecretReference:
    provider_key: str
    environment_variable: str
    secret_type: str
    reference_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.secret-reference/2",
            "provider_key": self.provider_key,
            "environment_variable": self.environment_variable,
            "secret_type": self.secret_type,
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "secret_value_fingerprinted": False,
            "reference_fingerprint": self.reference_fingerprint,
        }


@dataclass(frozen=True)
class SecretAvailabilityAttestation:
    provider_key: str
    reference_fingerprint: str
    available: bool
    attestation_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.secret-availability-attestation/1",
            "provider_key": self.provider_key,
            "reference_fingerprint": self.reference_fingerprint,
            "available": self.available,
            "secret_value_persisted": False,
            "secret_value_logged": False,
            "secret_value_fingerprinted": False,
            "attestation_fingerprint": self.attestation_fingerprint,
        }


def build_secret_reference(
    *,
    provider_key: str,
    environment_variable: str,
    secret_type: str,
) -> SecretReference:
    if not isinstance(provider_key, str) or not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")

    if (
        not isinstance(environment_variable, str)
        or not _ENV_RE.fullmatch(environment_variable)
    ):
        raise ValueError("INVALID_SECRET_ENVIRONMENT_VARIABLE")

    if secret_type not in _SECRET_TYPES:
        raise ValueError("INVALID_SECRET_TYPE")

    base = {
        "schema": "matrix.secret-reference/2",
        "provider_key": provider_key,
        "environment_variable": environment_variable,
        "secret_type": secret_type,
        "raw_secret_persisted": False,
        "raw_secret_logged": False,
        "secret_value_fingerprinted": False,
    }

    return SecretReference(
        provider_key=provider_key,
        environment_variable=environment_variable,
        secret_type=secret_type,
        reference_fingerprint=_sha(base),
    )


def resolve_secret_runtime(reference: SecretReference) -> str:
    expected = build_secret_reference(
        provider_key=reference.provider_key,
        environment_variable=reference.environment_variable,
        secret_type=reference.secret_type,
    )

    if expected != reference:
        raise ValueError("SECRET_REFERENCE_DERIVATION_MISMATCH")

    value = os.environ.get(reference.environment_variable)

    if value is None or not value:
        raise ValueError("SECRET_NOT_AVAILABLE")

    if "\n" in value or "\r" in value:
        raise ValueError("INVALID_SECRET_VALUE")

    return value


def attest_secret_available_runtime(
    reference: SecretReference,
) -> SecretAvailabilityAttestation:
    # Presence is checked, but secret material is never hashed/persisted/logged.
    value = resolve_secret_runtime(reference)
    if not value:
        raise ValueError("SECRET_NOT_AVAILABLE")

    base = {
        "schema": "matrix.secret-availability-attestation/1",
        "provider_key": reference.provider_key,
        "reference_fingerprint": reference.reference_fingerprint,
        "available": True,
        "secret_value_persisted": False,
        "secret_value_logged": False,
        "secret_value_fingerprinted": False,
    }

    return SecretAvailabilityAttestation(
        provider_key=reference.provider_key,
        reference_fingerprint=reference.reference_fingerprint,
        available=True,
        attestation_fingerprint=_sha(base),
    )


class SQLiteSecretReferenceRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS secret_references (
                    reference_fingerprint TEXT PRIMARY KEY,
                    provider_key TEXT NOT NULL,
                    environment_variable TEXT NOT NULL,
                    secret_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE (
                        provider_key,
                        environment_variable,
                        secret_type
                    )
                )
                """
            )

    def register(
        self,
        reference: SecretReference,
    ) -> SecretReference:
        expected = build_secret_reference(
            provider_key=reference.provider_key,
            environment_variable=reference.environment_variable,
            secret_type=reference.secret_type,
        )

        if expected != reference:
            raise ValueError("SECRET_REFERENCE_DERIVATION_MISMATCH")

        payload_json = _canonical_json(reference.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT reference_fingerprint, payload_sha256
                FROM secret_references
                WHERE
                    provider_key = ?
                    AND environment_variable = ?
                    AND secret_type = ?
                """,
                (
                    reference.provider_key,
                    reference.environment_variable,
                    reference.secret_type,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == reference.reference_fingerprint
                    and str(existing[1]) == payload_sha
                ):
                    return reference
                raise ValueError("SECRET_REFERENCE_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO secret_references (
                    reference_fingerprint,
                    provider_key,
                    environment_variable,
                    secret_type,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reference.reference_fingerprint,
                    reference.provider_key,
                    reference.environment_variable,
                    reference.secret_type,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return reference

    def get_verified(
        self,
        fingerprint: str,
    ) -> SecretReference | None:
        fingerprint = _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    provider_key,
                    environment_variable,
                    secret_type,
                    payload_json,
                    payload_sha256
                FROM secret_references
                WHERE reference_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        (
            provider_key,
            environment_variable,
            secret_type,
            payload_json,
            stored_sha,
        ) = row

        payload = json.loads(payload_json)
        actual_sha = sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError("SECRET_REFERENCE_PAYLOAD_HASH_MISMATCH")

        expected = build_secret_reference(
            provider_key=payload["provider_key"],
            environment_variable=payload["environment_variable"],
            secret_type=payload["secret_type"],
        )

        if (
            expected.reference_fingerprint != fingerprint
            or expected.payload() != payload
            or payload["provider_key"] != provider_key
            or payload["environment_variable"] != environment_variable
            or payload["secret_type"] != secret_type
        ):
            raise ValueError("SECRET_REFERENCE_REDERIVATION_MISMATCH")

        return expected
