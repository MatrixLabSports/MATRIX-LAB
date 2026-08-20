from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, TypeVar

from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_scheduling_authorization import (
    compute_provider_scheduling_queue_fingerprint,
)
from app.core.provider_scheduling_evidence import (
    SQLiteProviderSchedulingEvidenceLedger,
)


_ALLOWED_SPORTS = {"football", "tennis"}
T = TypeVar("T")


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


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    return value.lower()


def _provider_keys_from_queue(
    queue_manifest: Mapping[str, Any],
) -> tuple[str, ...]:
    queue = queue_manifest.get("queue")
    if not isinstance(queue, list):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    provider_keys: set[str] = set()

    for item in queue:
        if not isinstance(item, Mapping):
            raise ValueError("INVALID_QUEUE_ITEM")

        provider_key = item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")

        provider_keys.add(provider_key)

    return tuple(sorted(provider_keys))


@dataclass(frozen=True)
class ProviderExecutionPermit:
    sport: str
    queue_fingerprint: str
    authorization_fingerprint: str
    provider_keys: tuple[str, ...]
    decision_fingerprints: tuple[str, ...]
    permit_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-execution-permit/1",
            "sport": self.sport,
            "queue_fingerprint": self.queue_fingerprint,
            "authorization_fingerprint": (
                self.authorization_fingerprint
            ),
            "provider_keys": list(self.provider_keys),
            "decision_fingerprints": list(
                self.decision_fingerprints
            ),
            "permit_fingerprint": self.permit_fingerprint,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def verify_provider_execution_authorization(
    *,
    queue_manifest: Mapping[str, Any],
    authorization_fingerprint: str,
    scheduling_evidence_ledger: SQLiteProviderSchedulingEvidenceLedger,
    health_evidence_ledger: SQLiteProviderHealthEvidenceLedger,
    expected_sport: str | None = None,
) -> ProviderExecutionPermit:
    authorization_fp = _validate_hex64(
        "AUTHORIZATION_FINGERPRINT",
        authorization_fingerprint,
    )

    if expected_sport is not None and expected_sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_EXPECTED_SPORT")

    scheduling_integrity = scheduling_evidence_ledger.audit_integrity()
    if not scheduling_integrity.ok:
        raise ValueError("SCHEDULING_EVIDENCE_INTEGRITY_FAILED")

    health_integrity = health_evidence_ledger.audit_integrity()
    if not health_integrity.ok:
        raise ValueError("HEALTH_EVIDENCE_INTEGRITY_FAILED")

    authorization = (
        scheduling_evidence_ledger.get_by_authorization_fingerprint(
            authorization_fp
        )
    )
    if authorization is None:
        raise ValueError("MISSING_DURABLE_SCHEDULING_AUTHORIZATION")

    sport, queue_fingerprint = (
        compute_provider_scheduling_queue_fingerprint(
            queue_manifest,
            expected_sport=expected_sport,
        )
    )

    if authorization.get("sport") != sport:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if authorization.get("authorization_status") != "AUTHORIZED":
        raise ValueError("SCHEDULING_AUTHORIZATION_NOT_AUTHORIZED")

    if authorization.get("execution_eligible") is not True:
        raise ValueError("SCHEDULING_AUTHORIZATION_NOT_EXECUTION_ELIGIBLE")

    if authorization.get("queue_fingerprint") != queue_fingerprint:
        raise ValueError("SCHEDULING_QUEUE_FINGERPRINT_MISMATCH")

    if (
        authorization.get("authorization_fingerprint")
        != authorization_fp
    ):
        raise ValueError("AUTHORIZATION_FINGERPRINT_MISMATCH")

    if authorization.get("automatic_model_promotion") is not False:
        raise ValueError("AUTO_MODEL_PROMOTION_ENABLED")

    if authorization.get("automatic_provider_switch") is not False:
        raise ValueError("AUTO_PROVIDER_SWITCH_ENABLED")

    if authorization.get("automatic_wagering") is not False:
        raise ValueError("AUTO_WAGERING_ENABLED")

    provider_keys = _provider_keys_from_queue(queue_manifest)
    durable_provider_keys = tuple(
        sorted(authorization.get("provider_keys") or [])
    )

    if durable_provider_keys != provider_keys:
        raise ValueError("SCHEDULING_PROVIDER_SET_MISMATCH")

    durable_eligible_provider_keys = tuple(
        sorted(authorization.get("eligible_provider_keys") or [])
    )
    if durable_eligible_provider_keys != provider_keys:
        raise ValueError("SCHEDULING_ELIGIBLE_PROVIDER_SET_MISMATCH")

    if authorization.get("blocked_provider_keys"):
        raise ValueError("SCHEDULING_HAS_BLOCKED_PROVIDER")

    if authorization.get("missing_provider_keys"):
        raise ValueError("SCHEDULING_HAS_MISSING_PROVIDER")

    raw_decision_fingerprints = authorization.get(
        "decision_fingerprints"
    )
    if not isinstance(raw_decision_fingerprints, list):
        raise ValueError("INVALID_DECISION_FINGERPRINTS")

    decision_fingerprints = tuple(
        _validate_hex64("DECISION_FINGERPRINT", value)
        for value in raw_decision_fingerprints
    )

    if len(decision_fingerprints) != len(
        set(decision_fingerprints)
    ):
        raise ValueError("DUPLICATE_DECISION_FINGERPRINT")

    durable_health_by_provider: dict[str, Mapping[str, Any]] = {}

    for decision_fp in decision_fingerprints:
        payload = health_evidence_ledger.get_by_decision_fingerprint(
            decision_fp
        )

        if payload is None:
            raise ValueError(
                f"MISSING_DURABLE_HEALTH_EVIDENCE:{decision_fp}"
            )

        if payload.get("sport") != sport:
            raise ValueError("HEALTH_EVIDENCE_SPORT_MISMATCH")

        provider_key = payload.get("provider_key")
        if provider_key not in provider_keys:
            raise ValueError("HEALTH_EVIDENCE_PROVIDER_MISMATCH")

        if provider_key in durable_health_by_provider:
            raise ValueError("MULTIPLE_HEALTH_DECISIONS_FOR_PROVIDER")

        if payload.get("decision_status") != "ELIGIBLE":
            raise ValueError(
                f"PROVIDER_NOT_ELIGIBLE_AT_EXECUTION:{provider_key}"
            )

        if payload.get("scheduling_eligible") is not True:
            raise ValueError(
                f"PROVIDER_NOT_SCHEDULABLE_AT_EXECUTION:{provider_key}"
            )

        if payload.get("automatic_provider_switch") is not False:
            raise ValueError("HEALTH_EVIDENCE_AUTO_SWITCH_ENABLED")

        durable_health_by_provider[provider_key] = payload

    if tuple(sorted(durable_health_by_provider)) != provider_keys:
        raise ValueError(
            "INCOMPLETE_DURABLE_HEALTH_EVIDENCE_AT_EXECUTION"
        )

    base = {
        "schema": "matrix.provider-execution-permit/1",
        "sport": sport,
        "queue_fingerprint": queue_fingerprint,
        "authorization_fingerprint": authorization_fp,
        "provider_keys": list(provider_keys),
        "decision_fingerprints": sorted(decision_fingerprints),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderExecutionPermit(
        sport=sport,
        queue_fingerprint=queue_fingerprint,
        authorization_fingerprint=authorization_fp,
        provider_keys=provider_keys,
        decision_fingerprints=tuple(
            sorted(decision_fingerprints)
        ),
        permit_fingerprint=_sha256(base),
    )


def execute_with_provider_authorization(
    *,
    queue_manifest: Mapping[str, Any],
    authorization_fingerprint: str,
    scheduling_evidence_ledger: SQLiteProviderSchedulingEvidenceLedger,
    health_evidence_ledger: SQLiteProviderHealthEvidenceLedger,
    executor: Callable[..., T],
    executor_kwargs: Mapping[str, Any],
    expected_sport: str | None = None,
) -> T:
    if not callable(executor):
        raise ValueError("INVALID_EXECUTOR")

    if not isinstance(executor_kwargs, Mapping):
        raise ValueError("INVALID_EXECUTOR_KWARGS")

    verify_provider_execution_authorization(
        queue_manifest=queue_manifest,
        authorization_fingerprint=authorization_fingerprint,
        scheduling_evidence_ledger=scheduling_evidence_ledger,
        health_evidence_ledger=health_evidence_ledger,
        expected_sport=expected_sport,
    )

    call_kwargs = dict(executor_kwargs)

    if "queue_manifest" in call_kwargs:
        if call_kwargs["queue_manifest"] != queue_manifest:
            raise ValueError("EXECUTOR_QUEUE_MANIFEST_MISMATCH")
    else:
        call_kwargs["queue_manifest"] = queue_manifest

    return executor(**call_kwargs)
