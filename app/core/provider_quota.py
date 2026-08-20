from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Mapping, Protocol, Any


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
class ProviderQuotaPolicy:
    provider_key: str
    window_seconds: int
    max_request_units: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")
        _positive_int("WINDOW_SECONDS", self.window_seconds)
        _positive_int("MAX_REQUEST_UNITS", self.max_request_units)


@dataclass(frozen=True)
class ProviderQuotaDecision:
    allowed: bool
    provider_key: str
    request_units: int
    used_before: int
    used_after: int
    remaining_units: int
    window_start_epoch: int
    window_end_epoch: int
    retry_after_seconds: int
    reason_code: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-quota-decision/1",
            "allowed": self.allowed,
            "provider_key": self.provider_key,
            "request_units": self.request_units,
            "used_before": self.used_before,
            "used_after": self.used_after,
            "remaining_units": self.remaining_units,
            "window_start_epoch": self.window_start_epoch,
            "window_end_epoch": self.window_end_epoch,
            "retry_after_seconds": self.retry_after_seconds,
            "reason_code": self.reason_code,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


class ProviderQuotaExceeded(RuntimeError):
    def __init__(self, decision: ProviderQuotaDecision) -> None:
        self.decision = decision
        super().__init__(
            f"{decision.provider_key}:{decision.reason_code}:"
            f"retry_after={decision.retry_after_seconds}"
        )


class ProviderFetcher(Protocol):
    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class SQLiteProviderQuotaStore:
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
                CREATE TABLE IF NOT EXISTS provider_quota_usage (
                    provider_key TEXT NOT NULL,
                    window_start_epoch INTEGER NOT NULL,
                    window_seconds INTEGER NOT NULL,
                    used_units INTEGER NOT NULL,
                    PRIMARY KEY (provider_key, window_start_epoch, window_seconds),
                    CHECK (window_seconds > 0),
                    CHECK (used_units >= 0)
                )
                """
            )

    def reserve(
        self,
        *,
        policy: ProviderQuotaPolicy,
        request_units: int,
        now: datetime,
    ) -> ProviderQuotaDecision:
        units = _positive_int("REQUEST_UNITS", request_units)
        current = _aware_utc(now)
        epoch = int(current.timestamp())

        window_start = (
            epoch // policy.window_seconds
        ) * policy.window_seconds
        window_end = window_start + policy.window_seconds

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT used_units
                FROM provider_quota_usage
                WHERE provider_key = ?
                  AND window_start_epoch = ?
                  AND window_seconds = ?
                """,
                (
                    policy.provider_key,
                    window_start,
                    policy.window_seconds,
                ),
            ).fetchone()

            used_before = 0 if row is None else int(row[0])
            proposed = used_before + units

            if proposed > policy.max_request_units:
                connection.execute("ROLLBACK")
                return ProviderQuotaDecision(
                    allowed=False,
                    provider_key=policy.provider_key,
                    request_units=units,
                    used_before=used_before,
                    used_after=used_before,
                    remaining_units=max(
                        0,
                        policy.max_request_units - used_before,
                    ),
                    window_start_epoch=window_start,
                    window_end_epoch=window_end,
                    retry_after_seconds=max(0, window_end - epoch),
                    reason_code="PROVIDER_QUOTA_EXCEEDED",
                )

            if row is None:
                connection.execute(
                    """
                    INSERT INTO provider_quota_usage (
                        provider_key,
                        window_start_epoch,
                        window_seconds,
                        used_units
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        policy.provider_key,
                        window_start,
                        policy.window_seconds,
                        proposed,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE provider_quota_usage
                    SET used_units = ?
                    WHERE provider_key = ?
                      AND window_start_epoch = ?
                      AND window_seconds = ?
                    """,
                    (
                        proposed,
                        policy.provider_key,
                        window_start,
                        policy.window_seconds,
                    ),
                )

            connection.execute("COMMIT")

        return ProviderQuotaDecision(
            allowed=True,
            provider_key=policy.provider_key,
            request_units=units,
            used_before=used_before,
            used_after=proposed,
            remaining_units=max(
                0,
                policy.max_request_units - proposed,
            ),
            window_start_epoch=window_start,
            window_end_epoch=window_end,
            retry_after_seconds=0,
            reason_code="PASS",
        )

    def usage(
        self,
        *,
        policy: ProviderQuotaPolicy,
        now: datetime,
    ) -> int:
        current = _aware_utc(now)
        epoch = int(current.timestamp())
        window_start = (
            epoch // policy.window_seconds
        ) * policy.window_seconds

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT used_units
                FROM provider_quota_usage
                WHERE provider_key = ?
                  AND window_start_epoch = ?
                  AND window_seconds = ?
                """,
                (
                    policy.provider_key,
                    window_start,
                    policy.window_seconds,
                ),
            ).fetchone()

        return 0 if row is None else int(row[0])


class QuotaGuardedFetcher:
    def __init__(
        self,
        *,
        fetcher: ProviderFetcher,
        quota_store: SQLiteProviderQuotaStore,
        policies: Mapping[str, ProviderQuotaPolicy],
        clock: Callable[[], datetime],
    ) -> None:
        self.fetcher = fetcher
        self.quota_store = quota_store
        self.policies = dict(policies)
        self.clock = clock

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        provider_key = queue_item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key:
            raise ValueError("MISSING_PROVIDER_KEY")

        policy = self.policies.get(provider_key)
        if policy is None:
            raise ValueError("MISSING_PROVIDER_QUOTA_POLICY")

        if policy.provider_key != provider_key:
            raise ValueError("PROVIDER_QUOTA_POLICY_MISMATCH")

        request_units = queue_item.get("estimated_request_cost")
        if (
            isinstance(request_units, bool)
            or not isinstance(request_units, int)
            or request_units <= 0
        ):
            raise ValueError("INVALID_REQUEST_UNITS")

        decision = self.quota_store.reserve(
            policy=policy,
            request_units=request_units,
            now=self.clock(),
        )

        if not decision.allowed:
            raise ProviderQuotaExceeded(decision)

        return self.fetcher.fetch(queue_item)
