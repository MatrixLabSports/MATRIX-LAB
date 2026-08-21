from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderAttemptCertification:
    run_id: str
    ok: bool
    physical_attempt_count: int
    unique_permit_count: int
    fresh_permit_per_attempt: bool
    consumed_permit_per_attempt: bool
    unique_network_lifecycle_per_attempt: bool
    errors: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-attempt-certification/1"
            ),
            "run_id": self.run_id,
            "ok": self.ok,
            "physical_attempt_count": (
                self.physical_attempt_count
            ),
            "unique_permit_count": (
                self.unique_permit_count
            ),
            "fresh_permit_per_attempt": (
                self.fresh_permit_per_attempt
            ),
            "consumed_permit_per_attempt": (
                self.consumed_permit_per_attempt
            ),
            "unique_network_lifecycle_per_attempt": (
                self.unique_network_lifecycle_per_attempt
            ),
            "errors": list(self.errors),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def certify_provider_physical_attempts(
    *,
    run_id: str,
    audit_ledger,
    binding_store,
    network_permit_store,
    network_call_evidence_store,
) -> ProviderAttemptCertification:
    errors: list[str] = []
    binding_ids: list[str] = []
    permit_ids: list[str] = []

    events = tuple(
        audit_ledger.list_events(
            run_id
        )
    )

    terminal_provider_events = [
        event
        for event
        in events
        if event.get("event_type")
        in {
            "PROVIDER_CALL_COMPLETED",
            "PROVIDER_CALL_FAILED",
        }
    ]

    for event in terminal_provider_events:
        payload = event.get(
            "event_payload"
        )

        if not isinstance(
            payload,
            Mapping,
        ):
            errors.append(
                "INVALID_PROVIDER_CALL_TERMINAL_PAYLOAD"
            )
            continue

        ids = payload.get(
            "network_binding_evidence_ids"
        )

        if not isinstance(
            ids,
            list,
        ):
            errors.append(
                "NETWORK_BINDING_EVIDENCE_IDS_REQUIRED"
            )
            continue

        consumed = payload.get(
            "consumed_request_units"
        )

        if (
            isinstance(
                consumed,
                int,
            )
            and not isinstance(
                consumed,
                bool,
            )
            and consumed >= 0
            and consumed != len(ids)
        ):
            errors.append(
                "PHYSICAL_ATTEMPT_COUNT_MISMATCH"
            )

        for evidence_id in ids:
            if not isinstance(
                evidence_id,
                str,
            ):
                errors.append(
                    "INVALID_NETWORK_BINDING_EVIDENCE_ID"
                )
                continue

            evidence = (
                binding_store.get_verified(
                    evidence_id
                )
            )

            if evidence is None:
                errors.append(
                    "NETWORK_BINDING_EVIDENCE_MISSING"
                )
                continue

            if evidence.run_id != run_id:
                errors.append(
                    "ATTEMPT_BINDING_RUN_MISMATCH"
                )

            binding_ids.append(
                evidence_id
            )

            permit = (
                network_permit_store.get_verified(
                    evidence.permit_id
                )
            )

            if permit is None:
                errors.append(
                    "ATTEMPT_PERMIT_MISSING"
                )
                continue

            permit_ids.append(
                evidence.permit_id
            )

            if permit.get(
                "consumed_at"
            ) is None:
                errors.append(
                    "ATTEMPT_PERMIT_NOT_CONSUMED"
                )

            network_events = (
                network_call_evidence_store.list_verified_events_for_permit(
                    evidence.permit_id
                )
            )

            started = [
                item
                for item
                in network_events
                if item.get(
                    "event_type"
                )
                == "NETWORK_CALL_STARTED"
            ]

            terminal = [
                item
                for item
                in network_events
                if item.get(
                    "event_type"
                )
                in {
                    "NETWORK_CALL_COMPLETED",
                    "NETWORK_CALL_FAILED",
                }
            ]

            if len(started) != 1:
                errors.append(
                    "ATTEMPT_NETWORK_STARTED_COUNT"
                )

            if len(terminal) != 1:
                errors.append(
                    "ATTEMPT_NETWORK_TERMINAL_COUNT"
                )

    if len(set(binding_ids)) != len(binding_ids):
        errors.append(
            "NETWORK_BINDING_EVIDENCE_REUSED"
        )

    if len(set(permit_ids)) != len(permit_ids):
        errors.append(
            "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS"
        )

    physical_attempt_count = len(
        binding_ids
    )

    unique_permit_count = len(
        set(
            permit_ids
        )
    )

    fresh_permit_per_attempt = (
        physical_attempt_count
        == unique_permit_count
        and physical_attempt_count
        == len(
            permit_ids
        )
    )

    consumed_permit_per_attempt = (
        "ATTEMPT_PERMIT_NOT_CONSUMED"
        not in errors
        and "ATTEMPT_PERMIT_MISSING"
        not in errors
    )

    unique_network_lifecycle_per_attempt = (
        "ATTEMPT_NETWORK_STARTED_COUNT"
        not in errors
        and "ATTEMPT_NETWORK_TERMINAL_COUNT"
        not in errors
    )

    return ProviderAttemptCertification(
        run_id=run_id,
        ok=not errors,
        physical_attempt_count=(
            physical_attempt_count
        ),
        unique_permit_count=(
            unique_permit_count
        ),
        fresh_permit_per_attempt=(
            fresh_permit_per_attempt
        ),
        consumed_permit_per_attempt=(
            consumed_permit_per_attempt
        ),
        unique_network_lifecycle_per_attempt=(
            unique_network_lifecycle_per_attempt
        ),
        errors=tuple(
            errors
        ),
    )
