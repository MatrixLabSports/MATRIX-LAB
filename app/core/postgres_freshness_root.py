from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg

from app.core.freshness_root import (
    FreshnessReservation,
    FreshnessState,
)
from app.security.secrets import (
    EnvironmentSecretRef,
)


_POSTGRES_UNAVAILABLE = (
    "POSTGRES_FRESHNESS_ROOT_UNAVAILABLE"
)

_POSTGRES_OPERATION_FAILED = (
    "POSTGRES_FRESHNESS_ROOT_OPERATION_FAILED"
)

_POSTGRES_CORRUPT_ROW = (
    "POSTGRES_FRESHNESS_ROOT_CORRUPT_ROW"
)

_POSTGRES_COMMIT_OUTCOME_UNKNOWN = (
    "POSTGRES_FRESHNESS_ROOT_COMMIT_OUTCOME_UNKNOWN"
)


_POSTGRES_SCHEMA_MISSING = (
    "POSTGRES_FRESHNESS_ROOT_SCHEMA_MISSING"
)

_POSTGRES_SCHEMA_INCOMPATIBLE = (
    "POSTGRES_FRESHNESS_ROOT_SCHEMA_INCOMPATIBLE"
)

_POSTGRES_SCHEMA_VERSION = 1

_POSTGRES_SCHEMA_CONTRACT_ID = (
    "matrix.postgres-freshness-root/1"
)

_INVALID_NAMESPACE = (
    "FRESHNESS_ROOT_INVALID_NAMESPACE"
)

_INVALID_TRANSACTION_ID = (
    "FRESHNESS_ROOT_INVALID_TRANSACTION_ID"
)

_REGRESSION_FORBIDDEN = (
    "FRESHNESS_ROOT_REGRESSION_FORBIDDEN"
)

_SAME_SEQUENCE_DIVERGENCE = (
    "FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE"
)


class _CorruptAuthorityRow(
    ValueError
):
    pass


class _CommitOutcomeUnknown(
    ValueError
):
    pass



class _SchemaMissing(
    ValueError
):
    pass


class _SchemaIncompatible(
    ValueError
):
    pass


_SELECT_SCHEMA_CONTRACT = """
SELECT
    schema_version,
    contract_id
FROM matrix_security.matrix_freshness_root_schema
"""


_SELECT_COLUMNS = """
SELECT
    current_sequence_id,
    current_commitment_sha256,
    pending_transaction_id,
    pending_expected_sequence_id,
    pending_expected_commitment_sha256,
    pending_intended_sequence_id,
    pending_intended_commitment_sha256
FROM matrix_security.matrix_freshness_root
WHERE namespace = %s
"""


_SELECT_COLUMNS_FOR_UPDATE = """
SELECT
    current_sequence_id,
    current_commitment_sha256,
    pending_transaction_id,
    pending_expected_sequence_id,
    pending_expected_commitment_sha256,
    pending_intended_sequence_id,
    pending_intended_commitment_sha256
FROM matrix_security.matrix_freshness_root
WHERE namespace = %s
FOR UPDATE
"""


_INSERT_INITIAL = """
INSERT INTO matrix_security.matrix_freshness_root (
    namespace,
    current_sequence_id,
    current_commitment_sha256
)
VALUES (%s, %s, %s)
ON CONFLICT (namespace) DO NOTHING
"""


_SET_PENDING = """
UPDATE matrix_security.matrix_freshness_root
SET
    pending_transaction_id = %s,
    pending_expected_sequence_id = %s,
    pending_expected_commitment_sha256 = %s,
    pending_intended_sequence_id = %s,
    pending_intended_commitment_sha256 = %s
WHERE namespace = %s
"""


_SET_CURRENT_CLEAR_PENDING = """
UPDATE matrix_security.matrix_freshness_root
SET
    current_sequence_id = %s,
    current_commitment_sha256 = %s,
    pending_transaction_id = NULL,
    pending_expected_sequence_id = NULL,
    pending_expected_commitment_sha256 = NULL,
    pending_intended_sequence_id = NULL,
    pending_intended_commitment_sha256 = NULL
WHERE namespace = %s
"""


_CLEAR_PENDING = """
UPDATE matrix_security.matrix_freshness_root
SET pending_transaction_id = NULL,
    pending_expected_sequence_id = NULL,
    pending_expected_commitment_sha256 = NULL,
    pending_intended_sequence_id = NULL,
    pending_intended_commitment_sha256 = NULL
WHERE namespace = %s
"""


class PostgresFreshnessRoot:
    """
    PostgreSQL-backed FreshnessRoot.

    CURRENT/PENDING transitions are transactionally serialized.

    Stored authority rows are treated as security state:
    malformed or internally inconsistent rows fail closed and
    are never silently repaired.

    A COMMIT exception is classified separately because the
    server-side durability outcome can be unknowable to the
    client after acknowledgement loss.

    production_authorized remains permanently False at this
    implementation stage.
    """

    __slots__ = (
        "_dsn_secret_ref",
        "_connect_factory",
    )

    def __init__(
        self,
        *,
        dsn_secret_ref: EnvironmentSecretRef,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(
            dsn_secret_ref,
            EnvironmentSecretRef,
        ):
            raise TypeError(
                "POSTGRES_FRESHNESS_ROOT_SECRET_REFERENCE_REQUIRED"
            )

        if (
            connect_factory is not None
            and not callable(connect_factory)
        ):
            raise TypeError(
                "POSTGRES_FRESHNESS_ROOT_CONNECT_FACTORY_INVALID"
            )

        self._dsn_secret_ref = (
            dsn_secret_ref
        )

        self._connect_factory = (
            psycopg.connect
            if connect_factory is None
            else connect_factory
        )

    @property
    def production_authorized(
        self,
    ) -> bool:
        return False

    def __repr__(
        self,
    ) -> str:
        return (
            "PostgresFreshnessRoot("
            "dsn_secret_ref="
            "EnvironmentSecretRef("
            "variable_name="
            f"{self._dsn_secret_ref.variable_name!r}, "
            "min_length="
            f"{self._dsn_secret_ref.min_length}"
            "), "
            "connect_factory=<redacted>, "
            "production_authorized=False"
            ")"
        )

    @staticmethod
    def _normalize_namespace(
        namespace: str,
    ) -> str:
        if (
            not isinstance(namespace, str)
            or not namespace.strip()
        ):
            raise ValueError(
                _INVALID_NAMESPACE
            )

        return namespace.strip()

    @classmethod
    def _validate_state(
        cls,
        *,
        namespace: str,
        state: FreshnessState,
    ) -> FreshnessState:
        if not isinstance(
            state,
            FreshnessState,
        ):
            raise TypeError(
                "FRESHNESS_ROOT_STATE_REQUIRED"
            )

        normalized = (
            cls._normalize_namespace(
                namespace
            )
        )

        if state.namespace != normalized:
            raise ValueError(
                _INVALID_NAMESPACE
            )

        return state

    @staticmethod
    def _validate_transaction_id(
        transaction_id: str,
    ) -> str:
        if (
            not isinstance(
                transaction_id,
                str,
            )
            or not transaction_id.strip()
        ):
            raise ValueError(
                _INVALID_TRANSACTION_ID
            )

        return transaction_id.strip()

    @staticmethod
    def _validate_transition(
        *,
        expected: FreshnessState,
        intended: FreshnessState,
    ) -> None:
        if (
            intended.sequence_id
            < expected.sequence_id
        ):
            raise ValueError(
                _REGRESSION_FORBIDDEN
            )

        if (
            intended.sequence_id
            == expected.sequence_id
            and intended.commitment_sha256
            != expected.commitment_sha256
        ):
            raise ValueError(
                _SAME_SEQUENCE_DIVERGENCE
            )

    @staticmethod
    def _raise_corrupt_row() -> None:
        raise _CorruptAuthorityRow(
            _POSTGRES_CORRUPT_ROW
        )

    def _open_connection(
        self,
    ) -> Any:
        # Resolve the DSN only when an operation actually needs it.
        # The secret is removed from the local frame before a
        # normalized connection failure is raised.
        dsn = self._dsn_secret_ref.resolve()
        connection_failed = False

        try:
            return self._connect_factory(
                dsn
            )
        except Exception:
            connection_failed = True
        finally:
            dsn = None

        if connection_failed:
            raise ValueError(
                _POSTGRES_UNAVAILABLE
            )

    @staticmethod
    def _close_quietly(
        connection: Any,
    ) -> None:
        if connection is None:
            return

        close = getattr(
            connection,
            "close",
            None,
        )

        if not callable(close):
            return

        try:
            close()
        except Exception:
            pass

    @staticmethod
    def _rollback_quietly(
        connection: Any,
    ) -> None:
        if connection is None:
            return

        rollback = getattr(
            connection,
            "rollback",
            None,
        )

        if not callable(rollback):
            return

        try:
            rollback()
        except Exception:
            pass

    @staticmethod
    def _commit_or_unknown(
        connection: Any,
    ) -> None:
        commit_failed = False

        try:
            connection.commit()
        except Exception:
            # Never claim rollback/non-commit here.
            # PostgreSQL may have durably committed before the
            # client lost acknowledgement.
            commit_failed = True

        if commit_failed:
            raise _CommitOutcomeUnknown(
                _POSTGRES_COMMIT_OUTCOME_UNKNOWN
            )

    @staticmethod
    def _stored_state(
        *,
        namespace: str,
        sequence_id: Any,
        commitment_sha256: Any,
    ) -> FreshnessState:
        if (
            isinstance(sequence_id, bool)
            or not isinstance(sequence_id, int)
            or sequence_id < 0
        ):
            PostgresFreshnessRoot._raise_corrupt_row()

        if sequence_id == 0:
            if commitment_sha256 is not None:
                PostgresFreshnessRoot._raise_corrupt_row()

        else:
            if (
                not isinstance(
                    commitment_sha256,
                    str,
                )
                or len(commitment_sha256)
                != 64
            ):
                PostgresFreshnessRoot._raise_corrupt_row()

            try:
                int(
                    commitment_sha256,
                    16,
                )
            except ValueError:
                PostgresFreshnessRoot._raise_corrupt_row()

        try:
            return FreshnessState(
                namespace=namespace,
                sequence_id=sequence_id,
                commitment_sha256=commitment_sha256,
            )
        except Exception:
            raise _CorruptAuthorityRow(
                _POSTGRES_CORRUPT_ROW
            )

    @classmethod
    def _decode_row(
        cls,
        *,
        namespace: str,
        row: tuple[Any, ...],
    ) -> tuple[
        FreshnessState,
        FreshnessReservation | None,
    ]:
        if (
            not isinstance(
                row,
                (tuple, list),
            )
            or len(row) != 7
        ):
            cls._raise_corrupt_row()

        current = cls._stored_state(
            namespace=namespace,
            sequence_id=row[0],
            commitment_sha256=row[1],
        )

        transaction_id = row[2]
        expected_sequence = row[3]
        expected_commitment = row[4]
        intended_sequence = row[5]
        intended_commitment = row[6]

        # Fully empty pending state is valid.
        if (
            transaction_id is None
            and expected_sequence is None
            and expected_commitment is None
            and intended_sequence is None
            and intended_commitment is None
        ):
            return (
                current,
                None,
            )

        # A pending payload without its transaction identity is
        # never interpreted as "no reservation".
        if (
            not isinstance(
                transaction_id,
                str,
            )
            or not transaction_id.strip()
            or expected_sequence is None
            or intended_sequence is None
        ):
            cls._raise_corrupt_row()

        expected = cls._stored_state(
            namespace=namespace,
            sequence_id=expected_sequence,
            commitment_sha256=expected_commitment,
        )

        intended = cls._stored_state(
            namespace=namespace,
            sequence_id=intended_sequence,
            commitment_sha256=intended_commitment,
        )

        try:
            cls._validate_transition(
                expected=expected,
                intended=intended,
            )
        except Exception:
            raise _CorruptAuthorityRow(
                _POSTGRES_CORRUPT_ROW
            )

        # A valid outstanding reservation must have been prepared
        # from the authority state which is still CURRENT.
        if current != expected:
            cls._raise_corrupt_row()

        reservation = FreshnessReservation(
            namespace=namespace,
            transaction_id=(
                transaction_id.strip()
            ),
            expected=expected,
            intended=intended,
        )

        return (
            current,
            reservation,
        )

    @staticmethod
    def _driver_sqlstate(
        error: Exception,
    ) -> str | None:
        sqlstate = getattr(
            error,
            "sqlstate",
            None,
        )

        if isinstance(
            sqlstate,
            str,
        ):
            return sqlstate

        diagnostic = getattr(
            error,
            "diag",
            None,
        )

        sqlstate = getattr(
            diagnostic,
            "sqlstate",
            None,
        )

        return (
            sqlstate
            if isinstance(sqlstate, str)
            else None
        )

    @classmethod
    def _verify_schema_compatibility(
        cls,
        connection: Any,
    ) -> None:
        translated_error: Exception | None = None
        row = None

        try:
            cursor = connection.execute(
                _SELECT_SCHEMA_CONTRACT
            )

            row = cursor.fetchone()

        except Exception as error:
            sqlstate = cls._driver_sqlstate(
                error
            )

            if sqlstate in {
                "3F000",
                "42P01",
            }:
                translated_error = _SchemaMissing(
                    _POSTGRES_SCHEMA_MISSING
                )

            elif sqlstate in {
                "42703",
                "42804",
            }:
                translated_error = _SchemaIncompatible(
                    _POSTGRES_SCHEMA_INCOMPATIBLE
                )

            else:
                translated_error = ValueError(
                    _POSTGRES_OPERATION_FAILED
                )

        if translated_error is not None:
            raise translated_error

        if row is None:
            raise _SchemaMissing(
                _POSTGRES_SCHEMA_MISSING
            )

        if (
            not isinstance(
                row,
                (tuple, list),
            )
            or len(row) != 2
        ):
            raise _SchemaIncompatible(
                _POSTGRES_SCHEMA_INCOMPATIBLE
            )

        schema_version = row[0]
        contract_id = row[1]

        if (
            schema_version
            != _POSTGRES_SCHEMA_VERSION
            or contract_id
            != _POSTGRES_SCHEMA_CONTRACT_ID
        ):
            raise _SchemaIncompatible(
                _POSTGRES_SCHEMA_INCOMPATIBLE
            )

    @staticmethod
    def _select_row(
        connection: Any,
        *,
        namespace: str,
        for_update: bool,
    ) -> tuple[Any, ...] | None:
        sql = (
            _SELECT_COLUMNS_FOR_UPDATE
            if for_update
            else _SELECT_COLUMNS
        )

        cursor = connection.execute(
            sql,
            (
                namespace,
            ),
        )

        return cursor.fetchone()

    @staticmethod
    def _handle_operation_error(
        *,
        connection: Any,
        error: Exception,
    ) -> Exception:
        PostgresFreshnessRoot._rollback_quietly(
            connection
        )

        if isinstance(
            error,
            (
                _CorruptAuthorityRow,
                _CommitOutcomeUnknown,
                _SchemaMissing,
                _SchemaIncompatible,
            ),
        ):
            # These are already normalized MATRIX exceptions.
            # Remove any internal exception graph accumulated
            # before the public boundary returns them.
            error.__traceback__ = None
            error.__cause__ = None
            error.__context__ = None
            error.__suppress_context__ = True

            return error

        return ValueError(
            _POSTGRES_OPERATION_FAILED
        )

    def read(
        self,
        namespace: str,
    ) -> FreshnessState | None:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=False,
            )

            if row is None:
                return None

            current, _ = self._decode_row(
                namespace=normalized,
                row=row,
            )

            return current

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def initialize(
        self,
        *,
        namespace: str,
        state: FreshnessState,
    ) -> bool:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        state = self._validate_state(
            namespace=normalized,
            state=state,
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            cursor = connection.execute(
                _INSERT_INITIAL,
                (
                    normalized,
                    state.sequence_id,
                    state.commitment_sha256,
                ),
            )

            if cursor.rowcount == 1:
                self._commit_or_unknown(
                    connection
                )
                return True

            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=True,
            )

            if row is None:
                self._rollback_quietly(
                    connection
                )
                return False

            current, pending = (
                self._decode_row(
                    namespace=normalized,
                    row=row,
                )
            )

            result = (
                current == state
                and pending is None
            )

            self._rollback_quietly(
                connection
            )

            return result

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def read_pending(
        self,
        namespace: str,
    ) -> FreshnessReservation | None:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=False,
            )

            if row is None:
                return None

            _, pending = self._decode_row(
                namespace=normalized,
                row=row,
            )

            return pending

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def prepare(
        self,
        *,
        namespace: str,
        expected: FreshnessState,
        intended: FreshnessState,
        transaction_id: str,
    ) -> bool:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        expected = self._validate_state(
            namespace=normalized,
            state=expected,
        )

        intended = self._validate_state(
            namespace=normalized,
            state=intended,
        )

        transaction_id = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        self._validate_transition(
            expected=expected,
            intended=intended,
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=True,
            )

            if row is None:
                self._rollback_quietly(
                    connection
                )
                return False

            current, pending = (
                self._decode_row(
                    namespace=normalized,
                    row=row,
                )
            )

            if pending is not None:
                result = (
                    pending.transaction_id
                    == transaction_id
                    and pending.expected
                    == expected
                    and pending.intended
                    == intended
                )

                self._rollback_quietly(
                    connection
                )

                return result

            if current != expected:
                self._rollback_quietly(
                    connection
                )
                return False

            connection.execute(
                _SET_PENDING,
                (
                    transaction_id,
                    expected.sequence_id,
                    expected.commitment_sha256,
                    intended.sequence_id,
                    intended.commitment_sha256,
                    normalized,
                ),
            )

            self._commit_or_unknown(
                connection
            )

            return True

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def finalize(
        self,
        *,
        namespace: str,
        transaction_id: str,
        intended: FreshnessState,
    ) -> bool:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        intended = self._validate_state(
            namespace=normalized,
            state=intended,
        )

        transaction_id = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=True,
            )

            if row is None:
                self._rollback_quietly(
                    connection
                )
                return False

            current, pending = (
                self._decode_row(
                    namespace=normalized,
                    row=row,
                )
            )

            if pending is None:
                result = (
                    current == intended
                )

                self._rollback_quietly(
                    connection
                )

                return result

            if (
                pending.transaction_id
                != transaction_id
                or pending.intended
                != intended
            ):
                self._rollback_quietly(
                    connection
                )
                return False

            connection.execute(
                _SET_CURRENT_CLEAR_PENDING,
                (
                    intended.sequence_id,
                    intended.commitment_sha256,
                    normalized,
                ),
            )

            self._commit_or_unknown(
                connection
            )

            return True

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def abort(
        self,
        *,
        namespace: str,
        transaction_id: str,
        expected: FreshnessState,
    ) -> bool:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        expected = self._validate_state(
            namespace=normalized,
            state=expected,
        )

        transaction_id = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=True,
            )

            if row is None:
                self._rollback_quietly(
                    connection
                )
                return False

            current, pending = (
                self._decode_row(
                    namespace=normalized,
                    row=row,
                )
            )

            if pending is None:
                result = (
                    current == expected
                )

                self._rollback_quietly(
                    connection
                )

                return result

            if (
                pending.transaction_id
                != transaction_id
                or pending.expected
                != expected
            ):
                self._rollback_quietly(
                    connection
                )
                return False

            connection.execute(
                _CLEAR_PENDING,
                (
                    normalized,
                ),
            )

            self._commit_or_unknown(
                connection
            )

            return True

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error

    def compare_and_set(
        self,
        *,
        namespace: str,
        expected: FreshnessState | None,
        new: FreshnessState,
    ) -> bool:
        normalized = (
            self._normalize_namespace(
                namespace
            )
        )

        new = self._validate_state(
            namespace=normalized,
            state=new,
        )

        if expected is not None:
            expected = self._validate_state(
                namespace=normalized,
                state=expected,
            )

            self._validate_transition(
                expected=expected,
                intended=new,
            )

        connection = (
            self._open_connection()
        )

        operation_error: Exception | None = None

        try:
            self._verify_schema_compatibility(
                connection
            )
            if expected is None:
                cursor = connection.execute(
                    _INSERT_INITIAL,
                    (
                        normalized,
                        new.sequence_id,
                        new.commitment_sha256,
                    ),
                )

                if cursor.rowcount == 1:
                    self._commit_or_unknown(
                        connection
                    )
                    return True

                # Existing namespace must still be decoded before
                # returning False. Corrupt authority state may
                # never be silently treated as a normal CAS miss.
                row = self._select_row(
                    connection,
                    namespace=normalized,
                    for_update=True,
                )

                if row is None:
                    self._rollback_quietly(
                        connection
                    )
                    return False

                self._decode_row(
                    namespace=normalized,
                    row=row,
                )

                self._rollback_quietly(
                    connection
                )

                return False

            row = self._select_row(
                connection,
                namespace=normalized,
                for_update=True,
            )

            if row is None:
                self._rollback_quietly(
                    connection
                )
                return False

            current, pending = (
                self._decode_row(
                    namespace=normalized,
                    row=row,
                )
            )

            if (
                pending is not None
                or current != expected
            ):
                self._rollback_quietly(
                    connection
                )
                return False

            connection.execute(
                _SET_CURRENT_CLEAR_PENDING,
                (
                    new.sequence_id,
                    new.commitment_sha256,
                    normalized,
                ),
            )

            self._commit_or_unknown(
                connection
            )

            return True

        except Exception as error:
            operation_error = self._handle_operation_error(
                connection=connection,
                error=error,
            )

        finally:
            self._close_quietly(
                connection
            )

        if operation_error is not None:
            raise operation_error
