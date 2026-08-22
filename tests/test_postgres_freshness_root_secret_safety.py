from __future__ import annotations

import os
import traceback

import pytest

from app.core.postgres_freshness_root import (
    PostgresFreshnessRoot,
)
from app.security.secrets import (
    EnvironmentSecretRef,
)


SECRET_ENV = (
    "MATRIX_POSTGRES_GSEC_TEST_DSN_SECRET"
)

MARKER = (
    "MATRIX_"
    + "SYNTHETIC_"
    + "SECRET_"
    + "EXCEPTION_GRAPH"
)

DSN = (
    "postgresql://matrix_test:"
    + MARKER
    + "@127.0.0.1:1/"
    + "matrix_gsec"
    + "?sslmode=disable"
    + "&connect_timeout=1"
)

SCHEMA_CONTRACT = (
    "matrix.postgres-freshness-root/1"
)


def secret_ref() -> EnvironmentSecretRef:
    return EnvironmentSecretRef(
        variable_name=SECRET_ENV,
        min_length=16,
    )


def exception_graph_text(
    error: BaseException,
) -> str:
    parts: list[str] = []

    current: BaseException | None = (
        error
    )

    seen: set[int] = set()

    while (
        current is not None
        and id(current) not in seen
    ):
        seen.add(
            id(current)
        )

        parts.extend(
            (
                str(current),
                repr(current),
                "".join(
                    traceback.format_exception(
                        type(current),
                        current,
                        current.__traceback__,
                    )
                ),
            )
        )

        if current.__cause__ is not None:
            current = current.__cause__

        elif current.__context__ is not None:
            current = current.__context__

        else:
            current = None

    return "\n".join(parts)


def assert_secret_absent_from_graph(
    error: BaseException,
) -> None:
    rendered = exception_graph_text(
        error
    )

    assert MARKER not in rendered
    assert DSN not in rendered


def test_connection_failure_cannot_retain_secret_in_exception_graph(
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        DSN,
    )

    def connector(
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "synthetic-connector-failure:"
            + MARKER
        )

    root = PostgresFreshnessRoot(
        dsn_secret_ref=secret_ref(),
        connect_factory=connector,
    )

    with pytest.raises(
        ValueError
    ) as caught:
        root.read(
            "matrix/gsec/connector"
        )

    assert str(caught.value) == (
        "POSTGRES_FRESHNESS_ROOT_UNAVAILABLE"
    )

    assert_secret_absent_from_graph(
        caught.value
    )


class Cursor:
    def __init__(
        self,
        row,
    ):
        self._row = row

    def fetchone(self):
        return self._row


class OperationFailureConnection:
    def execute(
        self,
        sql,
        params=None,
    ):
        normalized = " ".join(
            str(sql).split()
        ).upper()

        if (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT_SCHEMA"
            in normalized
        ):
            return Cursor(
                (
                    1,
                    SCHEMA_CONTRACT,
                )
            )

        if (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT"
            in normalized
        ):
            raise RuntimeError(
                "synthetic-operation-failure:"
                + MARKER
            )

        raise AssertionError(
            "UNEXPECTED_SQL"
        )

    def rollback(self):
        return None

    def close(self):
        return None


def test_operation_failure_cannot_retain_secret_in_exception_graph(
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        DSN,
    )

    connection = (
        OperationFailureConnection()
    )

    root = PostgresFreshnessRoot(
        dsn_secret_ref=secret_ref(),
        connect_factory=(
            lambda *args, **kwargs: connection
        ),
    )

    with pytest.raises(
        ValueError
    ) as caught:
        root.read(
            "matrix/gsec/operation"
        )

    assert str(caught.value) == (
        "POSTGRES_FRESHNESS_ROOT_OPERATION_FAILED"
    )

    assert_secret_absent_from_graph(
        caught.value
    )


class SyntheticMissingSchemaError(
    RuntimeError
):
    sqlstate = "42P01"


class SchemaFailureConnection:
    def execute(
        self,
        sql,
        params=None,
    ):
        normalized = " ".join(
            str(sql).split()
        ).upper()

        if (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT_SCHEMA"
            in normalized
        ):
            raise SyntheticMissingSchemaError(
                "synthetic-schema-failure:"
                + MARKER
            )

        raise AssertionError(
            "AUTHORITY_QUERY_MUST_NOT_RUN"
        )

    def rollback(self):
        return None

    def close(self):
        return None


def test_schema_translation_cannot_retain_secret_in_exception_graph(
    monkeypatch,
):
    monkeypatch.setenv(
        SECRET_ENV,
        DSN,
    )

    connection = (
        SchemaFailureConnection()
    )

    root = PostgresFreshnessRoot(
        dsn_secret_ref=secret_ref(),
        connect_factory=(
            lambda *args, **kwargs: connection
        ),
    )

    with pytest.raises(
        ValueError
    ) as caught:
        root.read(
            "matrix/gsec/schema"
        )

    assert str(caught.value) == (
        "POSTGRES_FRESHNESS_ROOT_SCHEMA_MISSING"
    )

    assert_secret_absent_from_graph(
        caught.value
    )


# ============================================================
# GSEC_R2B_EXTENDED_SECRET_BOUNDARY
#
# The PostgreSQL freshness adapter is a credential-bearing
# trust boundary. Raw driver exception objects, tracebacks,
# causes and contexts must never escape through its public
# fail-closed errors.
# ============================================================


class GsecCommitFailureConnection:

    def commit(self):
        raise RuntimeError(
            "synthetic-commit-failure:"
            + MARKER
        )


def test_commit_failure_cannot_retain_secret_in_exception_graph():
    connection = (
        GsecCommitFailureConnection()
    )

    with pytest.raises(
        ValueError
    ) as caught:
        PostgresFreshnessRoot._commit_or_unknown(
            connection
        )

    assert str(caught.value) == (
        "POSTGRES_FRESHNESS_ROOT_COMMIT_OUTCOME_UNKNOWN"
    )

    assert_secret_absent_from_graph(
        caught.value
    )


_GSEC_SENSITIVE_METHODS = {
    "_open_connection",
    "_commit_or_unknown",
    "_stored_state",
    "_decode_row",
    "_verify_schema_compatibility",
    "_handle_operation_error",
}


def _gsec_sensitive_method_nodes():
    import ast
    from pathlib import Path

    source = Path(
        "app/core/postgres_freshness_root.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=(
            "app/core/"
            "postgres_freshness_root.py"
        ),
    )

    methods = {}

    for node in tree.body:
        if not isinstance(
            node,
            ast.ClassDef,
        ):
            continue

        if (
            node.name
            != "PostgresFreshnessRoot"
        ):
            continue

        for child in node.body:
            if not isinstance(
                child,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if child.name in (
                _GSEC_SENSITIVE_METHODS
            ):
                methods[
                    child.name
                ] = child

    assert set(methods) == (
        _GSEC_SENSITIVE_METHODS
    )

    return methods


def test_sensitive_adapter_has_no_explicit_exception_chaining():
    import ast

    methods = (
        _gsec_sensitive_method_nodes()
    )

    chained = []

    for name, method in methods.items():
        for node in ast.walk(
            method
        ):
            if not isinstance(
                node,
                ast.Raise,
            ):
                continue

            if node.cause is None:
                continue

            chained.append(
                (
                    name,
                    node.lineno,
                )
            )

    assert chained == []


def test_sensitive_adapter_has_no_raw_reraise_nodes():
    import ast

    methods = (
        _gsec_sensitive_method_nodes()
    )

    raw_reraises = []

    for name, method in methods.items():
        for node in ast.walk(
            method
        ):
            if not isinstance(
                node,
                ast.Raise,
            ):
                continue

            if node.exc is None:
                raw_reraises.append(
                    (
                        name,
                        node.lineno,
                        "bare-raise",
                    )
                )
                continue

            if (
                isinstance(
                    node.exc,
                    ast.Name,
                )
                and node.exc.id
                == "error"
            ):
                raw_reraises.append(
                    (
                        name,
                        node.lineno,
                        "raise-error",
                    )
                )

    assert raw_reraises == []


def test_operation_error_normalizer_does_not_raise_inside_helper():
    import ast

    methods = (
        _gsec_sensitive_method_nodes()
    )

    method = methods[
        "_handle_operation_error"
    ]

    raises = [
        node.lineno
        for node in ast.walk(
            method
        )
        if isinstance(
            node,
            ast.Raise,
        )
    ]

    # A normalized safe exception must be constructed/returned
    # here and raised only after the caller has left its raw
    # Exception handler. Raising from this helper while invoked
    # inside `except Exception as error` retains __context__.
    assert raises == []
