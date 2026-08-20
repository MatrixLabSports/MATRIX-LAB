from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Protocol

from app.core.provider_quota import ProviderQuotaExceeded


_ALLOWED_STATES = {"CLOSED", "OPEN", "HALF_OPEN"}


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"INVALID_{name}")
    return value


@dataclass(frozen=True)
class ProviderCircuitPolicy:
    provider_key: str
    failure_threshold: int
    cooldown_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")
        _positive_int("FAILURE_THRESHOLD", self.failure_threshold)
        _positive_int("COOLDOWN_SECONDS", self.cooldown_seconds)


@dataclass(frozen=True)
class ProviderCircuitDecision:
    allowed: bool
    provider_key: str
    state: str
    failure_count: int
    retry_after_seconds: int
    reason_code: str

    def __post_init__(self) -> None:
        if self.state not in _ALLOWED_STATES:
            raise ValueError("INVALID_CIRCUIT_STATE")

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-circuit-decision/1",
            "allowed": self.allowed,
            "provider_key": self.provider_key,
            "state": self.state,
            "failure_count": self.failure_count,
            "retry_after_seconds": self.retry_after_seconds,
            "reason_code": self.reason_code,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


class ProviderCircuitOpen(RuntimeError):
    def __init__(self, decision: ProviderCircuitDecision) -> None:
        self.decision = decision
        super().__init__(
            f"{decision.provider_key}:{decision.reason_code}:"
            f"retry_after={decision.retry_after_seconds}"
        )


class ProviderFetcher(Protocol):
    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class SQLiteProviderCircuitStore:
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
                CREATE TABLE IF NOT EXISTS provider_circuit_state (
                    provider_key TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    failure_count INTEGER NOT NULL,
                    opened_at_epoch INTEGER,
                    probe_in_flight INTEGER NOT NULL DEFAULT 0,
                    CHECK (state IN ('CLOSED', 'OPEN', 'HALF_OPEN')),
                    CHECK (failure_count >= 0),
                    CHECK (probe_in_flight IN (0, 1))
                )
                """
            )

    def _read_state(
        self,
        connection: sqlite3.Connection,
        provider_key: str,
    ) -> tuple[str, int, int | None, int]:
        row = connection.execute(
            """
            SELECT
                state,
                failure_count,
                opened_at_epoch,
                probe_in_flight
            FROM provider_circuit_state
            WHERE provider_key = ?
            """,
            (provider_key,),
        ).fetchone()

        if row is None:
            return "CLOSED", 0, None, 0

        return (
            str(row[0]),
            int(row[1]),
            None if row[2] is None else int(row[2]),
            int(row[3]),
        )

    def before_request(
        self,
        *,
        policy: ProviderCircuitPolicy,
        now: datetime,
    ) -> ProviderCircuitDecision:
        current = _aware_utc(now)
        epoch = int(current.timestamp())

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            (
                state,
                failure_count,
                opened_at,
                probe_in_flight,
            ) = self._read_state(connection, policy.provider_key)

            if state == "CLOSED":
                connection.execute("COMMIT")
                return ProviderCircuitDecision(
                    allowed=True,
                    provider_key=policy.provider_key,
                    state="CLOSED",
                    failure_count=failure_count,
                    retry_after_seconds=0,
                    reason_code="PASS",
                )

            if state == "OPEN":
                if opened_at is None:
                    connection.execute("ROLLBACK")
                    raise ValueError("OPEN_CIRCUIT_WITHOUT_TIMESTAMP")

                retry_after = max(
                    0,
                    opened_at + policy.cooldown_seconds - epoch,
                )

                if retry_after > 0:
                    connection.execute("COMMIT")
                    return ProviderCircuitDecision(
                        allowed=False,
                        provider_key=policy.provider_key,
                        state="OPEN",
                        failure_count=failure_count,
                        retry_after_seconds=retry_after,
                        reason_code="PROVIDER_CIRCUIT_OPEN",
                    )

                connection.execute(
                    """
                    INSERT INTO provider_circuit_state (
                        provider_key,
                        state,
                        failure_count,
                        opened_at_epoch,
                        probe_in_flight
                    )
                    VALUES (?, 'HALF_OPEN', ?, ?, 1)
                    ON CONFLICT(provider_key) DO UPDATE SET
                        state = 'HALF_OPEN',
                        failure_count = excluded.failure_count,
                        opened_at_epoch = excluded.opened_at_epoch,
                        probe_in_flight = 1
                    """,
                    (
                        policy.provider_key,
                        failure_count,
                        opened_at,
                    ),
                )
                connection.execute("COMMIT")

                return ProviderCircuitDecision(
                    allowed=True,
                    provider_key=policy.provider_key,
                    state="HALF_OPEN",
                    failure_count=failure_count,
                    retry_after_seconds=0,
                    reason_code="HALF_OPEN_PROBE",
                )

            if state == "HALF_OPEN":
                connection.execute("COMMIT")
                return ProviderCircuitDecision(
                    allowed=False,
                    provider_key=policy.provider_key,
                    state="HALF_OPEN",
                    failure_count=failure_count,
                    retry_after_seconds=0,
                    reason_code="HALF_OPEN_PROBE_IN_FLIGHT",
                )

            connection.execute("ROLLBACK")
            raise ValueError("INVALID_CIRCUIT_STATE")

    def record_success(
        self,
        *,
        policy: ProviderCircuitPolicy,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO provider_circuit_state (
                    provider_key,
                    state,
                    failure_count,
                    opened_at_epoch,
                    probe_in_flight
                )
                VALUES (?, 'CLOSED', 0, NULL, 0)
                ON CONFLICT(provider_key) DO UPDATE SET
                    state = 'CLOSED',
                    failure_count = 0,
                    opened_at_epoch = NULL,
                    probe_in_flight = 0
                """,
                (policy.provider_key,),
            )
            connection.execute("COMMIT")

    def record_failure(
        self,
        *,
        policy: ProviderCircuitPolicy,
        now: datetime,
    ) -> None:
        current = _aware_utc(now)
        epoch = int(current.timestamp())

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state, failure_count, _, _ = self._read_state(
                connection,
                policy.provider_key,
            )

            new_count = failure_count + 1
            should_open = (
                state == "HALF_OPEN"
                or new_count >= policy.failure_threshold
            )

            if should_open:
                connection.execute(
                    """
                    INSERT INTO provider_circuit_state (
                        provider_key,
                        state,
                        failure_count,
                        opened_at_epoch,
                        probe_in_flight
                    )
                    VALUES (?, 'OPEN', ?, ?, 0)
                    ON CONFLICT(provider_key) DO UPDATE SET
                        state = 'OPEN',
                        failure_count = excluded.failure_count,
                        opened_at_epoch = excluded.opened_at_epoch,
                        probe_in_flight = 0
                    """,
                    (
                        policy.provider_key,
                        new_count,
                        epoch,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO provider_circuit_state (
                        provider_key,
                        state,
                        failure_count,
                        opened_at_epoch,
                        probe_in_flight
                    )
                    VALUES (?, 'CLOSED', ?, NULL, 0)
                    ON CONFLICT(provider_key) DO UPDATE SET
                        state = 'CLOSED',
                        failure_count = excluded.failure_count,
                        opened_at_epoch = NULL,
                        probe_in_flight = 0
                    """,
                    (
                        policy.provider_key,
                        new_count,
                    ),
                )

            connection.execute("COMMIT")

    def snapshot(
        self,
        provider_key: str,
    ) -> Mapping[str, Any]:
        with self._connect() as connection:
            state, failures, opened_at, probe = self._read_state(
                connection,
                provider_key,
            )

        return {
            "provider_key": provider_key,
            "state": state,
            "failure_count": failures,
            "opened_at_epoch": opened_at,
            "probe_in_flight": bool(probe),
        }


class CircuitBreakerFetcher:
    def __init__(
        self,
        *,
        fetcher: ProviderFetcher,
        circuit_store: SQLiteProviderCircuitStore,
        policies: Mapping[str, ProviderCircuitPolicy],
        clock: Callable[[], datetime],
    ) -> None:
        self.fetcher = fetcher
        self.circuit_store = circuit_store
        self.policies = dict(policies)
        self.clock = clock

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        provider_key = queue_item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key:
            raise ValueError("MISSING_PROVIDER_KEY")

        policy = self.policies.get(provider_key)
        if policy is None:
            raise ValueError("MISSING_PROVIDER_CIRCUIT_POLICY")

        if policy.provider_key != provider_key:
            raise ValueError("PROVIDER_CIRCUIT_POLICY_MISMATCH")

        decision = self.circuit_store.before_request(
            policy=policy,
            now=self.clock(),
        )

        if not decision.allowed:
            raise ProviderCircuitOpen(decision)

        try:
            payload = self.fetcher.fetch(queue_item)
        except ProviderQuotaExceeded:
            # Quota refusal means no provider request was made.
            # It must not degrade provider health.
            if decision.state == "HALF_OPEN":
                self.circuit_store.record_success(policy=policy)
            raise
        except Exception:
            self.circuit_store.record_failure(
                policy=policy,
                now=self.clock(),
            )
            raise

        self.circuit_store.record_success(policy=policy)
        return payload
