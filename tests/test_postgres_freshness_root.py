from __future__ import annotations

import importlib
import inspect

import pytest

from app.core.freshness_root import FreshnessRoot
from app.security.secrets import EnvironmentSecretRef


MODULE = "app.core.postgres_freshness_root"
SECRET_ENV = "MATRIX_POSTGRES_FRESHNESS_DSN_SECRET"

TEST_DSN = (
    "postgresql://matrix_test:"
    "very-long-test-password@"
    "db.example.test:5432/"
    "matrix_freshness?"
    "sslmode=verify-full"
)


def adapter_class():
    try:
        module = importlib.import_module(MODULE)
    except ModuleNotFoundError:
        pytest.fail(
            "POSTGRES_FRESHNESS_ROOT_MODULE_MISSING"
        )

    cls = getattr(
        module,
        "PostgresFreshnessRoot",
        None,
    )

    if cls is None:
        pytest.fail(
            "POSTGRES_FRESHNESS_ROOT_CLASS_MISSING"
        )

    return cls


def secret_ref():
    return EnvironmentSecretRef(
        variable_name=SECRET_ENV,
        min_length=16,
    )


def make_root(connect_factory):
    cls = adapter_class()

    return cls(
        dsn_secret_ref=secret_ref(),
        connect_factory=connect_factory,
    )


def test_postgres_freshness_root_class_exists():
    assert (
        adapter_class().__name__
        == "PostgresFreshnessRoot"
    )


def test_constructor_has_safe_reference_and_connection_seam():
    signature = inspect.signature(
        adapter_class().__init__
    )

    parameters = signature.parameters

    assert "dsn_secret_ref" in parameters
    assert "connect_factory" in parameters
    assert "dsn" not in parameters
    assert "database_url" not in parameters
    assert "production_authorized" not in parameters


def test_construction_does_not_connect_or_resolve_secret(
    monkeypatch,
):
    monkeypatch.delenv(
        SECRET_ENV,
        raising=False,
    )

    calls = []

    def forbidden_connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError(
            "connection attempted during construction"
        )

    root = make_root(
        forbidden_connect
    )

    assert calls == []
    assert root.production_authorized is False


def test_adapter_satisfies_freshness_root_protocol():
    cls = adapter_class()

    for method in (
        "read",
        "initialize",
        "read_pending",
        "prepare",
        "finalize",
        "abort",
        "compare_and_set",
    ):
        assert hasattr(cls, method)

    root = make_root(
        lambda *a, **k: None
    )

    assert isinstance(
        root,
        FreshnessRoot,
    )


def test_production_authorization_defaults_false():
    root = make_root(
        lambda *a, **k: None
    )

    assert root.production_authorized is False

    signature = inspect.signature(
        type(root).__init__
    )

    assert (
        "production_authorized"
        not in signature.parameters
    )


def test_secret_is_resolved_just_in_time(
    monkeypatch,
):
    monkeypatch.delenv(
        SECRET_ENV,
        raising=False,
    )

    captured = []

    def offline_connect(*args, **kwargs):
        captured.append((args, kwargs))
        raise OSError(
            "simulated postgres offline"
        )

    root = make_root(
        offline_connect
    )

    assert captured == []

    monkeypatch.setenv(
        SECRET_ENV,
        TEST_DSN,
    )

    with pytest.raises(
        ValueError,
        match="POSTGRES_FRESHNESS_ROOT_UNAVAILABLE",
    ):
        root.read(
            "matrix/test/freshness"
        )

    assert len(captured) == 1

    args, kwargs = captured[0]

    assert TEST_DSN in (
        repr(args) + repr(kwargs)
    )


def test_missing_secret_blocks_before_connector(
    monkeypatch,
):
    monkeypatch.delenv(
        SECRET_ENV,
        raising=False,
    )

    calls = []

    def connector(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError(
            "connector must not execute"
        )

    root = make_root(
        connector
    )

    with pytest.raises(
        RuntimeError,
        match="missing secret",
    ):
        root.read(
            "matrix/test/freshness"
        )

    assert calls == []


def test_secret_material_not_retained_in_repr(
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        TEST_DSN,
    )

    root = make_root(
        lambda *a, **k: None
    )

    rendered = repr(root)

    assert TEST_DSN not in rendered
    assert (
        "very-long-test-password"
        not in rendered
    )


def test_connection_failure_normalized_fail_closed(
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        TEST_DSN,
    )

    def failing_connect(*args, **kwargs):
        raise ConnectionError(
            "driver connection failed"
        )

    root = make_root(
        failing_connect
    )

    with pytest.raises(
        ValueError
    ) as caught:
        root.read(
            "matrix/test/freshness"
        )

    assert str(caught.value) == (
        "POSTGRES_FRESHNESS_ROOT_UNAVAILABLE"
    )


def test_adapter_cannot_self_authorize_production():
    root = make_root(
        lambda *a, **k: None
    )

    assert root.production_authorized is False
