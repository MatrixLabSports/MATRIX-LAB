from types import SimpleNamespace

from app.core.provider_attempt_certification import (
    certify_provider_physical_attempts,
)


RUN_ID = "1" * 64


class AuditLedger:
    def __init__(self, binding_ids):
        self.binding_ids = binding_ids

    def list_events(self, run_id):
        assert run_id == RUN_ID
        return (
            {
                "event_type": (
                    "PROVIDER_CALL_COMPLETED"
                ),
                "event_payload": {
                    "consumed_request_units": len(
                        self.binding_ids
                    ),
                    "network_binding_evidence_ids": list(
                        self.binding_ids
                    ),
                },
            },
        )


class BindingStore:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_verified(self, evidence_id):
        return self.mapping.get(
            evidence_id
        )


class PermitStore:
    def __init__(self, consumed=True):
        self.consumed = consumed

    def get_verified(self, permit_id):
        return {
            "permit_id": permit_id,
            "consumed_at": (
                "2026-08-20T20:00:00+00:00"
                if self.consumed
                else None
            ),
        }


class NetworkCallStore:
    def list_verified_events_for_permit(
        self,
        permit_id,
    ):
        return (
            {
                "event_type": (
                    "NETWORK_CALL_STARTED"
                ),
            },
            {
                "event_type": (
                    "NETWORK_CALL_COMPLETED"
                ),
            },
        )


def test_two_physical_attempts_require_two_unique_consumed_permits():
    binding_ids = (
        "2" * 64,
        "3" * 64,
    )

    bindings = {
        binding_ids[0]: SimpleNamespace(
            run_id=RUN_ID,
            permit_id="4" * 64,
        ),
        binding_ids[1]: SimpleNamespace(
            run_id=RUN_ID,
            permit_id="5" * 64,
        ),
    }

    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                binding_ids
            ),
            binding_store=BindingStore(
                bindings
            ),
            network_permit_store=PermitStore(),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
        )
    )

    assert certification.ok is True
    assert (
        certification.physical_attempt_count
        == 2
    )
    assert (
        certification.unique_permit_count
        == 2
    )
    assert (
        certification.fresh_permit_per_attempt
        is True
    )
    assert (
        certification.consumed_permit_per_attempt
        is True
    )
    assert (
        certification.unique_network_lifecycle_per_attempt
        is True
    )


def test_permit_reuse_across_retry_attempts_fails_closed():
    binding_ids = (
        "2" * 64,
        "3" * 64,
    )

    reused = "4" * 64

    bindings = {
        binding_ids[0]: SimpleNamespace(
            run_id=RUN_ID,
            permit_id=reused,
        ),
        binding_ids[1]: SimpleNamespace(
            run_id=RUN_ID,
            permit_id=reused,
        ),
    }

    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                binding_ids
            ),
            binding_store=BindingStore(
                bindings
            ),
            network_permit_store=PermitStore(),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
        )
    )

    assert certification.ok is False
    assert (
        "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS"
        in certification.errors
    )
    assert (
        certification.fresh_permit_per_attempt
        is False
    )


def test_unconsumed_permit_fails_attempt_certification():
    binding_id = "2" * 64

    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                (binding_id,)
            ),
            binding_store=BindingStore(
                {
                    binding_id: (
                        SimpleNamespace(
                            run_id=RUN_ID,
                            permit_id="4" * 64,
                        )
                    ),
                }
            ),
            network_permit_store=(
                PermitStore(
                    consumed=False
                )
            ),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
        )
    )

    assert certification.ok is False
    assert (
        "ATTEMPT_PERMIT_NOT_CONSUMED"
        in certification.errors
    )
