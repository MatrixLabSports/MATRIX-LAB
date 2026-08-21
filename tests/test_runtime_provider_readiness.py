from types import SimpleNamespace

from app.core.runtime_reconciliation import (
    reconcile_runtime_provider_readiness,
)


RUN_ID = "1" * 64


class AuditLedger:
    def list_events(self, run_id):
        assert run_id == RUN_ID
        return ()


class IntentStore:
    def audit_integrity(self):
        return True

    def list_verified_for_run(self, run_id):
        assert run_id == RUN_ID
        return ()

    def get_by_permit(self, permit_id):
        return None


class EmptyBindingStore:
    def get_verified(self, evidence_id):
        return None


class EmptyPermitStore:
    def get_verified(self, permit_id):
        return None


class EmptyNetworkCallStore:
    def list_verified_events_for_permit(
        self,
        permit_id,
    ):
        return ()


class EmptyRecoveryStore:
    def get_by_permit(self, permit_id):
        return None


class EmptyContractEndpointStore:
    def authorize(self, **kwargs):
        raise AssertionError(
            "no intents should be authorized"
        )


def test_runtime_provider_readiness_fails_closed_for_empty_run_and_missing_rights():
    report = (
        reconcile_runtime_provider_readiness(
            base_report=SimpleNamespace(
                errors=(),
                report_fingerprint=(
                    "2" * 64
                ),
            ),
            run_id=RUN_ID,
            audit_ledger=AuditLedger(),
            binding_store=(
                EmptyBindingStore()
            ),
            network_permit_store=(
                EmptyPermitStore()
            ),
            network_call_evidence_store=(
                EmptyNetworkCallStore()
            ),
            attempt_intent_store=(
                IntentStore()
            ),
            interruption_recovery_store=(
                EmptyRecoveryStore()
            ),
            contract_endpoint_binding_store=(
                EmptyContractEndpointStore()
            ),
            rights_decision=(
                SimpleNamespace(
                    authorized=False
                )
            ),
        )
    )

    assert report["ok"] is False
    assert (
        "PROVIDER_RIGHTS_NOT_AUTHORIZED"
        in report["errors"]
    )
    assert any(
        "NO_PHYSICAL_ATTEMPTS_TO_CERTIFY"
        in error
        for error
        in report["errors"]
    )
    assert (
        report[
            "real_provider_execution_authorized"
        ]
        is False
    )
