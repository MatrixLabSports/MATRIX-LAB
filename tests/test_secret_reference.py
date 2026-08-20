import json
import sqlite3

import pytest

from app.core.secret_reference import (
    SQLiteSecretReferenceRegistry,
    attest_secret_available_runtime,
    build_secret_reference,
    resolve_secret_runtime,
)


def reference():
    return build_secret_reference(
        provider_key="provider-x",
        environment_variable="MATRIX_PROVIDER_X_API_KEY",
        secret_type="API_KEY",
    )


def test_secret_reference_contains_no_raw_secret():
    value = reference()
    payload = value.payload()

    assert "secret_value" not in payload
    assert payload["raw_secret_persisted"] is False
    assert payload["raw_secret_logged"] is False
    assert payload["secret_value_fingerprinted"] is False


def test_secret_reference_is_durable_without_secret(tmp_path):
    registry = SQLiteSecretReferenceRegistry(
        tmp_path / "refs.db"
    )
    value = reference()

    registry.register(value)
    loaded = registry.get_verified(
        value.reference_fingerprint
    )

    assert loaded == value


def test_secret_presence_attestation_never_hashes_secret(
    monkeypatch,
):
    value = reference()
    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    attestation = attest_secret_available_runtime(value)

    assert attestation.available is True
    assert (
        "runtime-only-value"
        not in json.dumps(attestation.payload())
    )
    assert (
        attestation.payload()["secret_value_fingerprinted"]
        is False
    )


def test_secret_is_resolved_only_from_runtime_environment(
    monkeypatch,
):
    value = reference()

    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    assert resolve_secret_runtime(value) == "runtime-only-value"

    monkeypatch.delenv(
        "MATRIX_PROVIDER_X_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="SECRET_NOT_AVAILABLE",
    ):
        attest_secret_available_runtime(value)


def test_rehashed_secret_reference_tamper_fails_closed(tmp_path):
    path = tmp_path / "refs.db"
    registry = SQLiteSecretReferenceRegistry(path)
    value = reference()
    registry.register(value)

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM secret_references
                WHERE reference_fingerprint = ?
                """,
                (value.reference_fingerprint,),
            ).fetchone()[0]
        )

        payload["secret_type"] = "TOKEN"

        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

        import hashlib
        payload_sha = hashlib.sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        connection.execute(
            """
            UPDATE secret_references
            SET payload_json = ?, payload_sha256 = ?
            WHERE reference_fingerprint = ?
            """,
            (
                payload_json,
                payload_sha,
                value.reference_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="SECRET_REFERENCE_REDERIVATION_MISMATCH",
    ):
        registry.get_verified(
            value.reference_fingerprint
        )
