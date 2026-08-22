from __future__ import annotations

import re

from dataclasses import dataclass
from threading import RLock
from typing import Protocol, runtime_checkable


_HEX64 = re.compile(
    r"[0-9a-f]{64}"
)


FRESHNESS_ROOT_INVALID_NAMESPACE = (
    "FRESHNESS_ROOT_INVALID_NAMESPACE"
)

FRESHNESS_ROOT_INVALID_SEQUENCE = (
    "FRESHNESS_ROOT_INVALID_SEQUENCE"
)

FRESHNESS_ROOT_INVALID_COMMITMENT = (
    "FRESHNESS_ROOT_INVALID_COMMITMENT"
)

FRESHNESS_ROOT_REGRESSION_FORBIDDEN = (
    "FRESHNESS_ROOT_REGRESSION_FORBIDDEN"
)

FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE = (
    "FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE"
)

FRESHNESS_ROOT_COMPARE_AND_SET_CONFLICT = (
    "FRESHNESS_ROOT_COMPARE_AND_SET_CONFLICT"
)

FRESHNESS_ROOT_NOT_AUTHORIZED_FOR_PRODUCTION = (
    "FRESHNESS_ROOT_NOT_AUTHORIZED_FOR_PRODUCTION"
)

FRESHNESS_ROOT_INVALID_TRANSACTION_ID = (
    "FRESHNESS_ROOT_INVALID_TRANSACTION_ID"
)

FRESHNESS_ROOT_INVALID_RESERVATION = (
    "FRESHNESS_ROOT_INVALID_RESERVATION"
)


@dataclass(frozen=True)
class FreshnessState:
    namespace: str
    sequence_id: int
    commitment_sha256: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(
                self.namespace,
                str,
            )
            or not self.namespace.strip()
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_NAMESPACE
            )

        if (
            type(self.sequence_id) is not int
            or self.sequence_id < 0
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_SEQUENCE
            )

        if self.sequence_id == 0:
            if (
                self.commitment_sha256
                is not None
            ):
                raise ValueError(
                    FRESHNESS_ROOT_INVALID_COMMITMENT
                )

        elif (
            not isinstance(
                self.commitment_sha256,
                str,
            )
            or _HEX64.fullmatch(
                self.commitment_sha256
            )
            is None
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_COMMITMENT
            )


@dataclass(frozen=True)
class FreshnessReservation:
    namespace: str
    transaction_id: str
    expected: FreshnessState
    intended: FreshnessState

    def __post_init__(self) -> None:
        if (
            not isinstance(
                self.namespace,
                str,
            )
            or not self.namespace.strip()
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_NAMESPACE
            )

        if (
            not isinstance(
                self.transaction_id,
                str,
            )
            or not self.transaction_id.strip()
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_TRANSACTION_ID
            )

        if (
            self.expected.namespace
            != self.namespace
            or self.intended.namespace
            != self.namespace
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_RESERVATION
            )

        if (
            self.intended.sequence_id
            <= self.expected.sequence_id
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_RESERVATION
            )


@runtime_checkable
class FreshnessRoot(Protocol):
    @property
    def production_authorized(self) -> bool:
        ...

    def read(
        self,
        namespace: str,
    ) -> FreshnessState | None:
        ...

    def initialize(
        self,
        *,
        namespace: str,
        state: FreshnessState,
    ) -> bool:
        ...

    def read_pending(
        self,
        namespace: str,
    ) -> FreshnessReservation | None:
        ...

    def prepare(
        self,
        *,
        namespace: str,
        expected: FreshnessState,
        intended: FreshnessState,
        transaction_id: str,
    ) -> bool:
        ...

    def finalize(
        self,
        *,
        namespace: str,
        transaction_id: str,
        intended: FreshnessState,
    ) -> bool:
        ...

    def abort(
        self,
        *,
        namespace: str,
        transaction_id: str,
        expected: FreshnessState,
    ) -> bool:
        ...

    def compare_and_set(
        self,
        *,
        namespace: str,
        expected: FreshnessState | None,
        new: FreshnessState,
    ) -> bool:
        ...


def require_production_authorized(
    root: FreshnessRoot,
) -> None:
    if not root.production_authorized:
        raise ValueError(
            FRESHNESS_ROOT_NOT_AUTHORIZED_FOR_PRODUCTION
        )


class InMemoryFreshnessRoot:
    """
    Deterministic development/test implementation.

    This implementation is intentionally process-local and MUST NOT
    be treated as an independent production trust root.

    Reservation operations are atomic under one process-local lock so
    tests can verify protocol semantics deterministically. They do not
    provide a production durability or fault-domain guarantee.
    """

    def __init__(self) -> None:
        self._states: dict[
            str,
            FreshnessState,
        ] = {}

        self._pending: dict[
            str,
            FreshnessReservation,
        ] = {}

        self._lock = RLock()

    @property
    def production_authorized(self) -> bool:
        return False

    @staticmethod
    def _validate_namespace(
        namespace: str,
    ) -> str:
        if (
            not isinstance(
                namespace,
                str,
            )
            or not namespace.strip()
        ):
            raise ValueError(
                FRESHNESS_ROOT_INVALID_NAMESPACE
            )

        return namespace.strip()

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
                FRESHNESS_ROOT_INVALID_TRANSACTION_ID
            )

        return transaction_id.strip()

    @classmethod
    def _validate_state_namespace(
        cls,
        *,
        namespace: str,
        state: FreshnessState,
    ) -> None:
        normalized = cls._validate_namespace(
            namespace
        )

        if state.namespace != normalized:
            raise ValueError(
                FRESHNESS_ROOT_INVALID_NAMESPACE
            )

    def read(
        self,
        namespace: str,
    ) -> FreshnessState | None:
        normalized = self._validate_namespace(
            namespace
        )

        with self._lock:
            return self._states.get(
                normalized
            )

    def initialize(
        self,
        *,
        namespace: str,
        state: FreshnessState,
    ) -> bool:
        normalized = self._validate_namespace(
            namespace
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=state,
        )

        with self._lock:
            current = self._states.get(
                normalized
            )

            pending = self._pending.get(
                normalized
            )

            if pending is not None:
                return False

            if current is None:
                self._states[
                    normalized
                ] = state
                return True

            return current == state

    def read_pending(
        self,
        namespace: str,
    ) -> FreshnessReservation | None:
        normalized = self._validate_namespace(
            namespace
        )

        with self._lock:
            return self._pending.get(
                normalized
            )

    def prepare(
        self,
        *,
        namespace: str,
        expected: FreshnessState,
        intended: FreshnessState,
        transaction_id: str,
    ) -> bool:
        normalized = self._validate_namespace(
            namespace
        )

        transaction = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=expected,
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=intended,
        )

        reservation = FreshnessReservation(
            namespace=normalized,
            transaction_id=transaction,
            expected=expected,
            intended=intended,
        )

        with self._lock:
            current = self._states.get(
                normalized
            )

            if current != expected:
                return False

            existing = self._pending.get(
                normalized
            )

            if existing is not None:
                return existing == reservation

            self._pending[
                normalized
            ] = reservation

            return True

    def finalize(
        self,
        *,
        namespace: str,
        transaction_id: str,
        intended: FreshnessState,
    ) -> bool:
        normalized = self._validate_namespace(
            namespace
        )

        transaction = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=intended,
        )

        with self._lock:
            current = self._states.get(
                normalized
            )

            pending = self._pending.get(
                normalized
            )

            if current == intended:
                if pending is None:
                    return True

                if (
                    pending.transaction_id
                    == transaction
                    and pending.intended
                    == intended
                ):
                    del self._pending[
                        normalized
                    ]
                    return True

                return False

            if pending is None:
                return False

            if (
                pending.transaction_id
                != transaction
                or pending.intended
                != intended
                or pending.expected
                != current
            ):
                return False

            self._states[
                normalized
            ] = intended

            del self._pending[
                normalized
            ]

            return True

    def abort(
        self,
        *,
        namespace: str,
        transaction_id: str,
        expected: FreshnessState,
    ) -> bool:
        normalized = self._validate_namespace(
            namespace
        )

        transaction = (
            self._validate_transaction_id(
                transaction_id
            )
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=expected,
        )

        with self._lock:
            current = self._states.get(
                normalized
            )

            pending = self._pending.get(
                normalized
            )

            if pending is None:
                return current == expected

            if (
                current != expected
                or pending.expected
                != expected
                or pending.transaction_id
                != transaction
            ):
                return False

            del self._pending[
                normalized
            ]

            return True

    def compare_and_set(
        self,
        *,
        namespace: str,
        expected: FreshnessState | None,
        new: FreshnessState,
    ) -> bool:
        normalized = self._validate_namespace(
            namespace
        )

        self._validate_state_namespace(
            namespace=normalized,
            state=new,
        )

        if expected is not None:
            self._validate_state_namespace(
                namespace=normalized,
                state=expected,
            )

        with self._lock:
            if (
                normalized
                in self._pending
            ):
                return False

            current = self._states.get(
                normalized
            )

            if current != expected:
                return False

            if current is not None:
                if (
                    new.sequence_id
                    < current.sequence_id
                ):
                    raise ValueError(
                        FRESHNESS_ROOT_REGRESSION_FORBIDDEN
                    )

                if (
                    new.sequence_id
                    == current.sequence_id
                    and new.commitment_sha256
                    != current.commitment_sha256
                ):
                    raise ValueError(
                        FRESHNESS_ROOT_SAME_SEQUENCE_DIVERGENCE
                    )

            self._states[
                normalized
            ] = new

            return True
