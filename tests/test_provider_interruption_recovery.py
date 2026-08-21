from datetime import datetime, timezone

import pytest

from app.core.provider_interruption_recovery import (
    SQLiteProviderInterruptionRecoveryStore,
    recover_started_only_network_attempt,
    reconcile_network_attempt_with_recovery,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)

RUN_ID = "1" * 64
PERMIT_ID = "2" * 64
QUEUE_FP = "3" * 64


class PermitStore:
    def __init__(self, *, consumed=True):
        self.consumed = consumed

    def get_verified(self, permit_id):
        assert permit_id == PERMIT_ID
        return {
            "permit_id": permit_id,
            "run_id": RUN_ID,
            "provider_key": "api_football",
            "consumed_at": (
                NOW.isoformat()
                if self.consumed
                else None
            ),
        }


class StartedOnlyCallStore:
    def list_verified_events_for_permit(
        self,
        permit_id,
    ):
        assert permit_id == PERMIT_ID
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


def test_started_only_attempt_becomes_interrupted_unknown_outcome(
    tmp_path,
):
    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    evidence = (
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint=(
                QUEUE_FP
            ),
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            network_permit_store=(
                PermitStore()
            ),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=(
                recovery_store
            ),
        )
    )

    assert (
        evidence.status
        == "INTERRUPTED_UNKNOWN_OUTCOME"
    )
    assert evidence.safe_to_retry is False
    assert (
        evidence.request_units_refunded
        is False
    )

    state = (
        reconcile_network_attempt_with_recovery(
            permit_id=PERMIT_ID,
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=(
                recovery_store
            ),
        )
    )

    assert (
        state.state
        == "INTERRUPTED_UNKNOWN_OUTCOME"
    )
    assert state.safe_to_retry is False
    assert recovery_store.audit_integrity() is True


def test_recovery_is_idempotent_and_does_not_refund_or_reuse_permit(
    tmp_path,
):
    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    first = recover_started_only_network_attempt(
        run_id=RUN_ID,
        provider_key="api_football",
        queue_item_fingerprint=QUEUE_FP,
        permit_id=PERMIT_ID,
        reason_code="CRASH_RECOVERY",
        now=NOW,
        network_permit_store=PermitStore(),
        network_call_evidence_store=(
            StartedOnlyCallStore()
        ),
        recovery_store=recovery_store,
    )

    second = recover_started_only_network_attempt(
        run_id=RUN_ID,
        provider_key="api_football",
        queue_item_fingerprint=QUEUE_FP,
        permit_id=PERMIT_ID,
        reason_code="CRASH_RECOVERY",
        now=NOW,
        network_permit_store=PermitStore(),
        network_call_evidence_store=(
            StartedOnlyCallStore()
        ),
        recovery_store=recovery_store,
    )

    assert first == second
    assert first.safe_to_retry is False
    assert (
        first.request_units_refunded
        is False
    )


def test_completed_attempt_cannot_be_recovered_as_interrupted(
    tmp_path,
):
    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    with pytest.raises(
        ValueError,
        match=(
            "INTERRUPTION_TERMINAL_EVENT_ALREADY_EXISTS"
        ),
    ):
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint=(
                QUEUE_FP
            ),
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            network_permit_store=PermitStore(),
            network_call_evidence_store=(
                CompletedCallStore()
            ),
            recovery_store=recovery_store,
        )


def test_unconsumed_permit_cannot_receive_recovery_evidence(
    tmp_path,
):
    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    with pytest.raises(
        ValueError,
        match=(
            "INTERRUPTION_REQUIRES_CONSUMED_PERMIT"
        ),
    ):
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint=QUEUE_FP,
            permit_id=PERMIT_ID,
            reason_code="CRASH_RECOVERY",
            now=NOW,
            network_permit_store=PermitStore(
                consumed=False
            ),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=recovery_store,
        )


def test_second_recovery_with_conflicting_reason_is_rejected(
    tmp_path,
):
    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    recover_started_only_network_attempt(
        run_id=RUN_ID,
        provider_key="api_football",
        queue_item_fingerprint=QUEUE_FP,
        permit_id=PERMIT_ID,
        reason_code="CRASH_RECOVERY",
        now=NOW,
        network_permit_store=PermitStore(),
        network_call_evidence_store=(
            StartedOnlyCallStore()
        ),
        recovery_store=recovery_store,
    )

    with pytest.raises(
        ValueError,
        match=(
            "INTERRUPTION_RECOVERY_ALREADY_RECORDED"
        ),
    ):
        recover_started_only_network_attempt(
            run_id=RUN_ID,
            provider_key="api_football",
            queue_item_fingerprint=QUEUE_FP,
            permit_id=PERMIT_ID,
            reason_code="HOST_SHUTDOWN",
            now=NOW,
            network_permit_store=PermitStore(),
            network_call_evidence_store=(
                StartedOnlyCallStore()
            ),
            recovery_store=recovery_store,
        )
