from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from app.core.provider_health_snapshot import ProviderHealthSnapshot


_ALLOWED_SPORTS = {"football", "tennis"}


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_rate(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"INVALID_{name}")

    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"INVALID_{name}")

    return numeric


@dataclass(frozen=True)
class ProviderHealthPolicy:
    provider_key: str
    min_terminal_calls: int
    max_failure_rate: float
    max_zero_consumption_refusal_rate: float
    require_known_consumption: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise ValueError("INVALID_PROVIDER_KEY")

        if (
            isinstance(self.min_terminal_calls, bool)
            or not isinstance(self.min_terminal_calls, int)
            or self.min_terminal_calls < 1
        ):
            raise ValueError("INVALID_MIN_TERMINAL_CALLS")

        object.__setattr__(
            self,
            "max_failure_rate",
            _validate_rate(
                "MAX_FAILURE_RATE",
                self.max_failure_rate,
            ),
        )
        object.__setattr__(
            self,
            "max_zero_consumption_refusal_rate",
            _validate_rate(
                "MAX_ZERO_CONSUMPTION_REFUSAL_RATE",
                self.max_zero_consumption_refusal_rate,
            ),
        )

        if not isinstance(self.require_known_consumption, bool):
            raise ValueError("INVALID_REQUIRE_KNOWN_CONSUMPTION")

    def fingerprint(self) -> str:
        return _sha256(
            {
                "schema": "matrix.provider-health-policy/1",
                "provider_key": self.provider_key,
                "min_terminal_calls": self.min_terminal_calls,
                "max_failure_rate": self.max_failure_rate,
                "max_zero_consumption_refusal_rate": (
                    self.max_zero_consumption_refusal_rate
                ),
                "require_known_consumption": self.require_known_consumption,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }
        )


@dataclass(frozen=True)
class ProviderHealthDecision:
    provider_key: str
    sport: str
    decision_status: str
    scheduling_eligible: bool
    terminal_calls: int
    failure_rate: float | None
    zero_consumption_refusal_rate: float | None
    policy_fingerprint: str
    snapshot_fingerprint: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-health-decision/1",
            "provider_key": self.provider_key,
            "sport": self.sport,
            "decision_status": self.decision_status,
            "scheduling_eligible": self.scheduling_eligible,
            "terminal_calls": self.terminal_calls,
            "failure_rate": self.failure_rate,
            "zero_consumption_refusal_rate": (
                self.zero_consumption_refusal_rate
            ),
            "policy_fingerprint": self.policy_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "reason_codes": list(self.reason_codes),
            "decision_fingerprint": self.decision_fingerprint,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def evaluate_provider_health(
    *,
    snapshot: ProviderHealthSnapshot,
    policy: ProviderHealthPolicy,
    expected_sport: str | None = None,
) -> ProviderHealthDecision:
    if expected_sport is not None and expected_sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_EXPECTED_SPORT")

    reasons: list[str] = []

    if snapshot.provider_key != policy.provider_key:
        reasons.append("PROVIDER_POLICY_MISMATCH")

    if snapshot.sport not in _ALLOWED_SPORTS:
        reasons.append("INVALID_SNAPSHOT_SPORT")

    if expected_sport is not None and snapshot.sport != expected_sport:
        reasons.append("SPORT_BOUNDARY_VIOLATION")

    if snapshot.snapshot_status != "VALID":
        reasons.append("SNAPSHOT_NOT_VALID")

    terminal_calls = snapshot.calls_completed + snapshot.calls_failed

    if terminal_calls < policy.min_terminal_calls:
        reasons.append("INSUFFICIENT_OBSERVATIONS")

    failure_rate = snapshot.failure_rate

    if failure_rate is None:
        reasons.append("UNKNOWN_FAILURE_RATE")
    elif failure_rate > policy.max_failure_rate:
        reasons.append("FAILURE_RATE_EXCEEDED")

    if terminal_calls == 0:
        zero_refusal_rate = None
        reasons.append("UNKNOWN_ZERO_REFUSAL_RATE")
    else:
        zero_refusal_rate = (
            snapshot.zero_consumption_refusals / terminal_calls
        )
        if (
            zero_refusal_rate
            > policy.max_zero_consumption_refusal_rate
        ):
            reasons.append(
                "ZERO_CONSUMPTION_REFUSAL_RATE_EXCEEDED"
            )

    if (
        policy.require_known_consumption
        and snapshot.consumed_request_units is None
    ):
        reasons.append("UNKNOWN_REQUEST_CONSUMPTION")

    reason_codes = tuple(dict.fromkeys(reasons))

    hard_failures = {
        "PROVIDER_POLICY_MISMATCH",
        "INVALID_SNAPSHOT_SPORT",
        "SPORT_BOUNDARY_VIOLATION",
        "SNAPSHOT_NOT_VALID",
        "FAILURE_RATE_EXCEEDED",
        "ZERO_CONSUMPTION_REFUSAL_RATE_EXCEEDED",
        "UNKNOWN_REQUEST_CONSUMPTION",
    }

    if any(reason in hard_failures for reason in reason_codes):
        decision_status = "INELIGIBLE"
        scheduling_eligible = False
    elif reason_codes:
        decision_status = "REVIEW_REQUIRED"
        scheduling_eligible = False
    else:
        decision_status = "ELIGIBLE"
        scheduling_eligible = True

    policy_fingerprint = policy.fingerprint()

    base = {
        "schema": "matrix.provider-health-decision/1",
        "provider_key": snapshot.provider_key,
        "sport": snapshot.sport,
        "decision_status": decision_status,
        "scheduling_eligible": scheduling_eligible,
        "terminal_calls": terminal_calls,
        "failure_rate": failure_rate,
        "zero_consumption_refusal_rate": zero_refusal_rate,
        "policy_fingerprint": policy_fingerprint,
        "snapshot_fingerprint": snapshot.snapshot_fingerprint,
        "reason_codes": list(reason_codes),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderHealthDecision(
        provider_key=snapshot.provider_key,
        sport=snapshot.sport,
        decision_status=decision_status,
        scheduling_eligible=scheduling_eligible,
        terminal_calls=terminal_calls,
        failure_rate=failure_rate,
        zero_consumption_refusal_rate=zero_refusal_rate,
        policy_fingerprint=policy_fingerprint,
        snapshot_fingerprint=snapshot.snapshot_fingerprint,
        reason_codes=reason_codes,
        decision_fingerprint=_sha256(base),
    )
