from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import time
from typing import Any, Callable, Mapping, Protocol

from app.core.provider_circuit_breaker import ProviderCircuitOpen
from app.core.provider_quota import ProviderQuotaExceeded


class ProviderFetcher(Protocol):
    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class RetryableProviderError(RuntimeError):
    """Provider/network failure explicitly safe for bounded retry."""


class NonRetryableProviderError(RuntimeError):
    """Provider failure that must fail closed without retry."""


@dataclass(frozen=True)
class ProviderRetryPolicy:
    provider_key: str
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float = 0.15

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")

        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ValueError("INVALID_MAX_ATTEMPTS")

        for name, value in (
            ("BASE_DELAY_SECONDS", self.base_delay_seconds),
            ("MAX_DELAY_SECONDS", self.max_delay_seconds),
            ("JITTER_RATIO", self.jitter_ratio),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"INVALID_{name}")

        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("MAX_DELAY_BELOW_BASE_DELAY")

        if self.jitter_ratio > 1:
            raise ValueError("JITTER_RATIO_ABOVE_ONE")

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-retry-policy/1",
            "provider_key": self.provider_key,
            "max_attempts": self.max_attempts,
            "base_delay_seconds": float(self.base_delay_seconds),
            "max_delay_seconds": float(self.max_delay_seconds),
            "jitter_ratio": float(self.jitter_ratio),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class ProviderRetryExhausted(RuntimeError):
    provider_key: str
    attempts: int
    last_error_type: str

    def __str__(self) -> str:
        return (
            f"{self.provider_key}:PROVIDER_RETRY_EXHAUSTED:"
            f"attempts={self.attempts}:last={self.last_error_type}"
        )


def _validate_queue_fingerprint(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("INVALID_QUEUE_ITEM_FINGERPRINT")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError("INVALID_QUEUE_ITEM_FINGERPRINT") from error

    return value.lower()


def retry_delay_seconds(
    *,
    policy: ProviderRetryPolicy,
    queue_item_fingerprint: str,
    retry_number: int,
) -> float:
    if (
        isinstance(retry_number, bool)
        or not isinstance(retry_number, int)
        or retry_number < 1
    ):
        raise ValueError("INVALID_RETRY_NUMBER")

    fingerprint = _validate_queue_fingerprint(queue_item_fingerprint)

    base = min(
        float(policy.max_delay_seconds),
        float(policy.base_delay_seconds) * (2 ** (retry_number - 1)),
    )

    if base == 0 or policy.jitter_ratio == 0:
        return base

    seed = sha256(
        f"{fingerprint}:{retry_number}".encode("utf-8")
    ).digest()

    unit = int.from_bytes(seed[:8], "big") / float((1 << 64) - 1)
    centered = (unit * 2.0) - 1.0
    factor = 1.0 + centered * float(policy.jitter_ratio)

    return max(
        0.0,
        min(float(policy.max_delay_seconds), base * factor),
    )


def is_retryable_provider_error(error: BaseException) -> bool:
    if isinstance(
        error,
        (
            ProviderQuotaExceeded,
            ProviderCircuitOpen,
            NonRetryableProviderError,
            ValueError,
        ),
    ):
        return False

    return isinstance(
        error,
        (
            RetryableProviderError,
            TimeoutError,
            ConnectionError,
        ),
    )


class BoundedRetryFetcher:
    def __init__(
        self,
        *,
        fetcher: ProviderFetcher,
        policies: Mapping[str, ProviderRetryPolicy],
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fetcher = fetcher
        self.policies = dict(policies)
        self.sleeper = sleeper

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        provider_key = queue_item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key:
            raise ValueError("MISSING_PROVIDER_KEY")

        policy = self.policies.get(provider_key)
        if policy is None:
            raise ValueError("MISSING_PROVIDER_RETRY_POLICY")

        if policy.provider_key != provider_key:
            raise ValueError("PROVIDER_RETRY_POLICY_MISMATCH")

        fingerprint = _validate_queue_fingerprint(
            queue_item.get("queue_item_fingerprint")
        )

        last_error: BaseException | None = None

        for attempt in range(1, policy.max_attempts + 1):
            try:
                return self.fetcher.fetch(queue_item)
            except Exception as error:
                last_error = error

                if not is_retryable_provider_error(error):
                    raise

                if attempt >= policy.max_attempts:
                    break

                delay = retry_delay_seconds(
                    policy=policy,
                    queue_item_fingerprint=fingerprint,
                    retry_number=attempt,
                )
                self.sleeper(delay)

        assert last_error is not None

        raise ProviderRetryExhausted(
            provider_key=provider_key,
            attempts=policy.max_attempts,
            last_error_type=type(last_error).__name__,
        ) from last_error
