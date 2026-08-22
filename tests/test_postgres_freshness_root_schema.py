from __future__ import annotations

from pathlib import Path

import pytest

from app.core.postgres_freshness_root import (
    PostgresFreshnessRoot,
)
from app.security.secrets import (
    EnvironmentSecretRef,
)


DDL_PATH = Path(
    "database/postgres/freshness_root/"
    "V001__create_freshness_root_authority.sql"
)

SCHEMA_NAME = "matrix_security"

AUTHORITY_TABLE = (
    "matrix_security.matrix_freshness_root"
)

CONTRACT_TABLE = (
    "matrix_security.matrix_freshness_root_schema"
)

SCHEMA_VERSION = 1

CONTRACT_ID = (
    "matrix.postgres-freshness-root/1"
)

SECRET_ENV = (
    "MATRIX_POSTGRES_FRESHNESS_DSN_SECRET"
)

TEST_DSN = (
    "postgresql://matrix_test:"
    "very-long-test-password@"
    "db.example.test:5432/"
    "matrix_freshness?"
    "sslmode=verify-full"
)

NAMESPACE = (
    "matrix/test/schema-contract"
)

SCHEMA_MISSING = (
    "POSTGRES_FRESHNESS_ROOT_SCHEMA_MISSING"
)

SCHEMA_INCOMPATIBLE = (
    "POSTGRES_FRESHNESS_ROOT_SCHEMA_INCOMPATIBLE"
)


def ddl_text():
    if not DDL_PATH.exists():
        pytest.fail(
            "POSTGRES_FRESHNESS_ROOT_DDL_ARTIFACT_MISSING"
        )

    return DDL_PATH.read_text(
        encoding="utf-8-sig"
    )


def normalized_ddl():
    return " ".join(
        ddl_text().split()
    ).upper()


class Cursor:
    def __init__(
        self,
        row=None,
    ):
        self._row = row
        self.rowcount = 0

    def fetchone(self):
        return self._row


class SchemaProbeConnection:
    def __init__(
        self,
        *,
        schema_row,
    ):
        self.schema_row = schema_row
        self.sql = []
        self.closed = False
        self.rollback_count = 0

    def execute(
        self,
        sql,
        params=None,
    ):
        normalized = " ".join(
            str(sql).split()
        ).upper()

        self.sql.append(
            (
                normalized,
                tuple(
                    ()
                    if params is None
                    else params
                ),
            )
        )

        if (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT_SCHEMA"
            in normalized
        ):
            return Cursor(
                self.schema_row
            )

        if (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT"
            in normalized
        ):
            return Cursor(
                None
            )

        raise AssertionError(
            "UNEXPECTED_SQL:"
            + normalized
        )

    def rollback(
        self,
    ):
        self.rollback_count += 1

    def close(
        self,
    ):
        self.closed = True


def make_root(
    monkeypatch,
    connection,
):
    monkeypatch.setenv(
        SECRET_ENV,
        TEST_DSN,
    )

    def connect(
        dsn,
    ):
        assert dsn == TEST_DSN
        return connection

    return PostgresFreshnessRoot(
        dsn_secret_ref=(
            EnvironmentSecretRef(
                variable_name=SECRET_ENV,
                min_length=16,
            )
        ),
        connect_factory=connect,
    )


def test_versioned_postgres_ddl_artifact_exists():
    assert DDL_PATH.is_file()


def test_ddl_is_explicit_transactional_v001_and_not_silent_rebaseline():
    text = normalized_ddl()

    assert DDL_PATH.name == (
        "V001__create_freshness_root_authority.sql"
    )

    assert text.startswith(
        "BEGIN;"
    )

    assert text.endswith(
        "COMMIT;"
    )

    # Initial authority bootstrap must not silently accept an
    # unknown pre-existing object with incompatible structure.
    assert "IF NOT EXISTS" not in text


def test_ddl_uses_dedicated_security_schema_and_qualified_tables():
    text = normalized_ddl()

    assert (
        "CREATE SCHEMA MATRIX_SECURITY"
        in text
    )

    assert (
        "CREATE TABLE "
        "MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT_SCHEMA"
        in text
    )

    assert (
        "CREATE TABLE "
        "MATRIX_SECURITY.MATRIX_FRESHNESS_ROOT"
        in text
    )


def test_ddl_has_exact_schema_compatibility_sentinel():
    text = ddl_text()

    assert (
        "schema_version"
        in text
    )

    assert (
        "contract_id"
        in text
    )

    assert (
        CONTRACT_ID
        in text
    )

    assert (
        "matrix_freshness_root_schema"
        in text
    )


def test_ddl_namespace_is_primary_key_and_nonempty():
    text = normalized_ddl()

    assert (
        "NAMESPACE TEXT PRIMARY KEY"
        in text
    )

    assert (
        "BTRIM(NAMESPACE) <> ''"
        in text
    )


def test_ddl_current_state_is_structurally_valid():
    text = normalized_ddl()

    assert (
        "CURRENT_SEQUENCE_ID BIGINT NOT NULL"
        in text
    )

    assert (
        "CURRENT_SEQUENCE_ID >= 0"
        in text
    )

    assert (
        "CURRENT_SEQUENCE_ID = 0"
        in text
    )

    assert (
        "CURRENT_COMMITMENT_SHA256 IS NULL"
        in text
    )

    assert (
        "CURRENT_SEQUENCE_ID > 0"
        in text
    )

    assert (
        "CURRENT_COMMITMENT_SHA256 ~ "
        "'^[0-9A-F]{64}$'"
        in text
    )


def test_ddl_pending_state_is_all_or_none_and_matches_current():
    text = normalized_ddl()

    for token in (
        "PENDING_TRANSACTION_ID",
        "PENDING_EXPECTED_SEQUENCE_ID",
        "PENDING_EXPECTED_COMMITMENT_SHA256",
        "PENDING_INTENDED_SEQUENCE_ID",
        "PENDING_INTENDED_COMMITMENT_SHA256",
    ):
        assert token in text

    assert (
        "BTRIM(PENDING_TRANSACTION_ID) <> ''"
        in text
    )

    assert (
        "PENDING_EXPECTED_SEQUENCE_ID = "
        "CURRENT_SEQUENCE_ID"
        in text
    )

    assert (
        "PENDING_EXPECTED_COMMITMENT_SHA256 "
        "IS NOT DISTINCT FROM "
        "CURRENT_COMMITMENT_SHA256"
        in text
    )


def test_ddl_pending_intended_state_cannot_regress_or_same_seq_diverge():
    text = normalized_ddl()

    assert (
        "PENDING_INTENDED_SEQUENCE_ID >= "
        "PENDING_EXPECTED_SEQUENCE_ID"
        in text
    )

    assert (
        "PENDING_INTENDED_SEQUENCE_ID = "
        "PENDING_EXPECTED_SEQUENCE_ID"
        in text
    )

    assert (
        "PENDING_INTENDED_COMMITMENT_SHA256 "
        "IS NOT DISTINCT FROM "
        "PENDING_EXPECTED_COMMITMENT_SHA256"
        in text
    )


def test_runtime_adapter_has_no_ddl_and_uses_only_qualified_authority_table():
    source = Path(
        "app/core/postgres_freshness_root.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    upper = source.upper()

    assert "CREATE TABLE" not in upper
    assert "CREATE SCHEMA" not in upper
    assert "ALTER TABLE" not in upper
    assert "DROP TABLE" not in upper

    assert (
        "matrix_security.matrix_freshness_root"
        in source
    )

    # Once qualified, no runtime SQL statement may rely on
    # search_path for the authority table.
    sql_lines = [
        line.strip()
        for line in source.splitlines()
        if (
            "matrix_freshness_root"
            in line
            and
            "matrix_freshness_root_schema"
            not in line
        )
    ]

    assert sql_lines

    assert all(
        "matrix_security.matrix_freshness_root"
        in line
        for line in sql_lines
    )


def test_missing_schema_sentinel_fails_closed_before_authority_query(
    monkeypatch,
):
    connection = SchemaProbeConnection(
        schema_row=None
    )

    root = make_root(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        ValueError,
        match=SCHEMA_MISSING,
    ):
        root.read(
            NAMESPACE
        )

    assert connection.sql

    first_sql = connection.sql[0][0]

    assert (
        "MATRIX_SECURITY."
        "MATRIX_FRESHNESS_ROOT_SCHEMA"
        in first_sql
    )

    assert not any(
        (
            "MATRIX_SECURITY."
            "MATRIX_FRESHNESS_ROOT "
            in sql
        )
        for sql, _
        in connection.sql
    )


def test_incompatible_schema_sentinel_fails_closed_before_authority_query(
    monkeypatch,
):
    connection = SchemaProbeConnection(
        schema_row=(
            99,
            "wrong.contract",
        )
    )

    root = make_root(
        monkeypatch,
        connection,
    )

    with pytest.raises(
        ValueError,
        match=SCHEMA_INCOMPATIBLE,
    ):
        root.read(
            NAMESPACE
        )

    assert len(
        connection.sql
    ) == 1

    assert (
        "MATRIX_SECURITY."
        "MATRIX_FRESHNESS_ROOT_SCHEMA"
        in connection.sql[0][0]
    )


def test_compatible_schema_is_verified_before_authority_read(
    monkeypatch,
):
    connection = SchemaProbeConnection(
        schema_row=(
            SCHEMA_VERSION,
            CONTRACT_ID,
        )
    )

    root = make_root(
        monkeypatch,
        connection,
    )

    assert root.read(
        NAMESPACE
    ) is None

    assert len(
        connection.sql
    ) >= 2

    assert (
        "MATRIX_SECURITY."
        "MATRIX_FRESHNESS_ROOT_SCHEMA"
        in connection.sql[0][0]
    )

    assert (
        "MATRIX_SECURITY."
        "MATRIX_FRESHNESS_ROOT"
        in connection.sql[1][0]
    )
