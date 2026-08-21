from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.provider_interruption_recovery import (
    SQLiteProviderInterruptionRecoveryStore,
    recover_all_started_only_network_attempts,
    recover_started_only_network_attempt,
    reconcile_network_attempt_with_recovery,
    scan_started_only_network_attempts,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)

RUN_ID = "1" * 64
PERMIT_ID = "2" * 64


class IntentStore:
    def __init__(self):
        self.intent = SimpleNamespace(
            intent_id="3" * 64,
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint="4" * 64,
            permit_id=PERMIT_ID,
            endpoint_manifest_id="5" * 64,
            request_contract_id="6" * 64,
            request_contract_fingerprint="7" * 64,
            request_path="/fixtures",
        )

    def get_by_permit(self, permit_id):
        if permit_id != PERMIT_ID:
            return None
        return self.intent

    def list_verified_for_run(self, run_id):
        assert run_id == RUN_ID
        return (
            self.intent,
        )


class PermitStore:
    def get_verified(self, permit_id):
        assert permit_id == PERMIT_ID
        return {
            "permit_id": permit_id,
            "run_id": RUN_ID,
            "provider_key": "api_football",
            "endpoint_manifest_id": "5" * 64,
            "consumed_at": NOW.isoformat(),
        }


class BindingStore:
    def authorize(
        self,
        *,
        request_contract_id,
        endpoint_manifest_id,
        path,
        now,
    ):
        assert request_contract_id == "6" * 64
        assert endpoint_manifest_id == "5" * 64
        assert path == "/fixtures"
        return object()


class StartedOnlyCallStore:
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
        )


class CompletedCallStore:
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


def test_recovery_derives_queue_and_contract_from_pre_network_intent(
    tmp_path,
):
    store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    evidence = (
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            attempt_intent_store=(
                IntentStore()
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=store,
            contract_endpoint_binding_store=(
                BindingStore()
            ),
        )
    )

    assert (
        evidence.queue_item_fingerprint
        == "4" * 64
    )
    assert (
        evidence.pre_network_binding_intent_id
        == "3" * 64
    )
    assert (
        evidence.request_contract_id
        == "6" * 64
    )
    assert evidence.safe_to_retry is False
    assert (
        evidence.request_units_refunded
        is False
    )


def test_arbitrary_queue_fingerprint_cannot_be_supplied_to_recovery(
    tmp_path,
):
    with pytest.raises(
        TypeError,
    ):
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint="f" * 64,
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            attempt_intent_store=(
                IntentStore()
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=(
                SQLiteProviderInterruptionRecoveryStore(
                    tmp_path / "recovery.db"
                )
            ),
            contract_endpoint_binding_store=(
                BindingStore()
            ),
        )


def test_started_only_scan_is_deterministic_and_fail_closed(
    tmp_path,
):
    store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    states = scan_started_only_network_attempts(
        run_id=RUN_ID,
        attempt_intent_store=(
            IntentStore()
        ),
        network_call_evidence_store=(
            StartedOnlyCallStore()
        ),
        recovery_store=store,
    )

    assert len(states) == 1
    assert (
        states[0].state
        == "STARTED_WITHOUT_TERMINAL"
    )
    assert (
        states[0].safe_to_retry
        is False
    )

    recovered = (
        recover_all_started_only_network_attempts(
            run_id=RUN_ID,
            provider_key="api_football",
            reason_code="CRASH_RECOVERY",
            now=NOW,
            attempt_intent_store=(
                IntentStore()
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=store,
            contract_endpoint_binding_store=(
                BindingStore()
            ),
        )
    )

    assert len(recovered) == 1

    states = scan_started_only_network_attempts(
        run_id=RUN_ID,
        attempt_intent_store=(
            IntentStore()
        ),
        network_call_evidence_store=(
            StartedOnlyCallStore()
        ),
        recovery_store=store,
    )

    assert (
        states[0].state
        == "INTERRUPTED_UNKNOWN_OUTCOME"
    )


def test_terminal_attempt_cannot_be_recovered(
    tmp_path,
):
    with pytest.raises(
        ValueError,
        match=(
            "INTERRUPTION_TERMINAL_EVENT_ALREADY_EXISTS"
        ),
    ):
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            attempt_intent_store=(
                IntentStore()
            ),
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                CompletedCallStore()
            ),
            recovery_store=(
                SQLiteProviderInterruptionRecoveryStore(
                    tmp_path / "recovery.db"
                )
            ),
            contract_endpoint_binding_store=(
                BindingStore()
            ),
        )
