import os

import pytest

from app.core.secret_reference import (
    build_secret_reference,
    resolve_secret_runtime,
)


def test_secret_reference_contains_no_raw_secret():
    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable="MATRIX_PROVIDER_X_API_KEY",
        secret_type="API_KEY",
    )

    payload = reference.payload()

    assert "secret_value" not in payload
    assert payload["raw_secret_persisted"] is False
    assert payload["raw_secret_logged"] is False


def test_secret_is_resolved_only_from_runtime_environment(
    monkeypatch,
):
    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable="MATRIX_PROVIDER_X_TOKEN",
        secret_type="TOKEN",
    )

    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_TOKEN",
        "runtime-only-value",
    )

    assert (
        resolve_secret_runtime(reference)
        == "runtime-only-value"
    )

    monkeypatch.delenv(
        "MATRIX_PROVIDER_X_TOKEN",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="SECRET_NOT_AVAILABLE",
    ):
        resolve_secret_runtime(reference)
