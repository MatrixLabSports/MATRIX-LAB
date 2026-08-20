from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.provider_health_policy import ProviderHealthDecision


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


def _validate_queue_manifest(
    queue_manifest: Mapping[str, Any],
) -> tuple[str, tuple[Mapping[str, Any], ...]]:
    if not isinstance(queue_manifest, Mapping):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    sport = queue_manifest.get("sport")
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_QUEUE_SPORT")

    queue = queue_manifest.get("queue")
    if not isinstance(queue, list):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    validated: list[Mapping[str, Any]] = []

    for item in queue:
        if not isinstance(item, Mapping):
            raise ValueError("INVALID_QUEUE_ITEM")

        if item.get("sport") != sport:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        provider_key = item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")

        validated.append(item)

    return str(sport), tuple(validated)


@dataclass(frozen=True)
class ProviderSchedulingAuthorization:
    sport: str
    authorization_status: str
    execution_eligible: bool
    provider_keys: tuple[str, ...]
    eligible_provider_keys: tuple[str, ...]
    blocked_provider_keys: tuple[str, ...]
    missing_provider_keys: tuple[str, ...]
    decision_fingerprints: tuple[str, ...]
    reason_codes: tuple[str, ...]
    authorization_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-scheduling-authorization/1",
            "sport": self.sport,
            "authorization_status": self.authorization_status,
            "execution_eligible": self.execution_eligible,
            "provider_keys": list(self.provider_keys),
            "eligible_provider_keys": list(self.eligible_provider_keys),
            "blocked_provider_keys": list(self.blocked_provider_keys),
            "missing_provider_keys": list(self.missing_provider_keys),
            "decision_fingerprints": list(self.decision_fingerprints),
            "reason_codes": list(self.reason_codes),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def authorize_provider_scheduling(
    *,
    queue_manifest: Mapping[str, Any],
    health_decisions: Mapping[str, ProviderHealthDecision],
    expected_sport: str | None = None,
) -> ProviderSchedulingAuthorization:
    sport, queue = _validate_queue_manifest(queue_manifest)

    if expected_sport is not None:
        if expected_sport not in _ALLOWED_SPORTS:
            raise ValueError("INVALID_EXPECTED_SPORT")
        if sport != expected_sport:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if not isinstance(health_decisions, Mapping):
        raise ValueError("INVALID_HEALTH_DECISIONS")

    provider_keys = tuple(
        sorted({str(item["provider_key"]) for item in queue})
    )

    eligible: list[str] = []
    blocked: list[str] = []
    missing: list[str] = []
    decision_fingerprints: list[str] = []
    reasons: list[str] = []

    for provider_key in provider_keys:
        decision = health_decisions.get(provider_key)

        if decision is None:
            missing.append(provider_key)
            reasons.append(f"MISSING_HEALTH_DECISION:{provider_key}")
            continue

        if not isinstance(decision, ProviderHealthDecision):
            blocked.append(provider_key)
            reasons.append(f"INVALID_HEALTH_DECISION:{provider_key}")
            continue

        if decision.provider_key != provider_key:
            blocked.append(provider_key)
            reasons.append(f"PROVIDER_DECISION_MISMATCH:{provider_key}")
            continue

        if decision.sport != sport:
            blocked.append(provider_key)
            reasons.append(f"SPORT_BOUNDARY_VIOLATION:{provider_key}")
            continue

        decision_fingerprints.append(decision.decision_fingerprint)

        if (
            decision.decision_status == "ELIGIBLE"
            and decision.scheduling_eligible is True
        ):
            eligible.append(provider_key)
        else:
            blocked.append(provider_key)
            reasons.append(
                f"PROVIDER_NOT_ELIGIBLE:{provider_key}:"
                f"{decision.decision_status}"
            )

    if not provider_keys:
        authorization_status = "EMPTY_QUEUE"
        execution_eligible = True
    elif missing or blocked:
        authorization_status = "BLOCKED"
        execution_eligible = False
    else:
        authorization_status = "AUTHORIZED"
        execution_eligible = True

    reason_codes = tuple(dict.fromkeys(reasons))

    base = {
        "schema": "matrix.provider-scheduling-authorization/1",
        "sport": sport,
        "authorization_status": authorization_status,
        "execution_eligible": execution_eligible,
        "provider_keys": list(provider_keys),
        "eligible_provider_keys": sorted(eligible),
        "blocked_provider_keys": sorted(set(blocked)),
        "missing_provider_keys": sorted(missing),
        "decision_fingerprints": sorted(decision_fingerprints),
        "reason_codes": list(reason_codes),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderSchedulingAuthorization(
        sport=sport,
        authorization_status=authorization_status,
        execution_eligible=execution_eligible,
        provider_keys=provider_keys,
        eligible_provider_keys=tuple(sorted(eligible)),
        blocked_provider_keys=tuple(sorted(set(blocked))),
        missing_provider_keys=tuple(sorted(missing)),
        decision_fingerprints=tuple(sorted(decision_fingerprints)),
        reason_codes=reason_codes,
        authorization_fingerprint=_sha256(base),
    )
