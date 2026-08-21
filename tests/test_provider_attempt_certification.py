from types import SimpleNamespace

import pytest

from app.core.provider_attempt_certification import (
    certify_provider_physical_attempts,
    enforce_provider_attempt_certification,
)


RUN_ID = "1" * 64


class AuditLedger:
    def __init__(self, binding_ids):
        self.binding_ids = binding_ids

    def list_events(self, run_id):
        assert run_id == RUN_ID

        if not self.binding_ids:
            return ()

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
    def get_verified(self, permit_id):
        return {
            "permit_id": permit_id,
            "consumed_at": (
                "2026-08-20T20:00:00+00:00"
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


class IntentStore:
    def __init__(self, mapping):
        self.mapping = mapping

    def audit_integrity(self):
        return True

    def get_by_permit(self, permit_id):
        return self.mapping.get(
            permit_id
        )


def _binding(permit_id):
    return SimpleNamespace(
        run_id=RUN_ID,
        provider_key="api_football",
        queue_item_fingerprint="9" * 64,
        permit_id=permit_id,
        endpoint_manifest_id="8" * 64,
        request_contract_id="7" * 64,
        request_contract_fingerprint="6" * 64,
    )


def _intent(permit_id):
    return SimpleNamespace(
        run_id=RUN_ID,
        provider_key="api_football",
        queue_item_fingerprint="9" * 64,
        permit_id=permit_id,
        endpoint_manifest_id="8" * 64,
        request_contract_id="7" * 64,
        request_contract_fingerprint="6" * 64,
    )


def test_two_attempts_require_two_unique_permits_and_intents():
    ids = (
        "2" * 64,
        "3" * 64,
    )

    bindings = {
        ids[0]: _binding(
            "4" * 64
        ),
        ids[1]: _binding(
            "5" * 64
        ),
    }

    intents = {
        "4" * 64: _intent(
            "4" * 64
        ),
        "5" * 64: _intent(
            "5" * 64
        ),
    }

    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                ids
            ),
            binding_store=BindingStore(
                bindings
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
            attempt_intent_store=(
                IntentStore(
                    intents
                )
            ),
        )
    )

    assert certification.ok is True
    assert (
        certification.fresh_permit_per_attempt
        is True
    )
    assert (
        certification.attempt_intent_integrity
        is True
    )

    assert (
        enforce_provider_attempt_certification(
            certification
        )
        == certification
    )


def test_empty_run_fails_closed():
    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                ()
            ),
            binding_store=BindingStore(
                {}
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
            attempt_intent_store=(
                IntentStore(
                    {}
                )
            ),
        )
    )

    assert certification.ok is False
    assert (
        "NO_PHYSICAL_ATTEMPTS_TO_CERTIFY"
        in certification.errors
    )

    with pytest.raises(
        ValueError,
        match=(
            "PROVIDER_ATTEMPT_CERTIFICATION_FAILED"
        ),
    ):
        enforce_provider_attempt_certification(
            certification
        )


def test_permit_reuse_fails_closed():
    ids = (
        "2" * 64,
        "3" * 64,
    )

    reused = "4" * 64

    certification = (
        certify_provider_physical_attempts(
            run_id=RUN_ID,
            audit_ledger=AuditLedger(
                ids
            ),
            binding_store=BindingStore(
                {
                    ids[0]: _binding(
                        reused
                    ),
                    ids[1]: _binding(
                        reused
                    ),
                }
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                NetworkCallStore()
            ),
            attempt_intent_store=(
                IntentStore(
                    {
                        reused: _intent(
                            reused
                        ),
                    }
                )
            ),
        )
    )

    assert certification.ok is False
    assert (
        "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS"
        in certification.errors
    )
