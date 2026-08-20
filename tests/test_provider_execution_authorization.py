import sqlite3

import pytest

from app.core.provider_execution_authorization import (
    execute_with_provider_authorization,
    verify_provider_execution_authorization,
)
from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_health_policy import ProviderHealthDecision
from app.core.provider_scheduling_authorization import (
    authorize_provider_scheduling,
)
from app.core.provider_scheduling_evidence import (
    SQLiteProviderSchedulingEvidenceLedger,
)


def item(
    *,
    sport="tennis",
    provider_key="P1",
    char="1",
):
    return {
        "sport": sport,
        "subject_key": "PLAYER:1",
        "provider_key": provider_key,
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": 1,
        "source_fingerprint": "a" * 64,
    }


def manifest(*items, sport="tennis"):
    return {
        "sport": sport,
        "queue": list(items),
    }


def health_decision(
    *,
    provider_key="P1",
    sport="tennis",
    decision_char="d",
):
    return ProviderHealthDecision(
        provider_key=provider_key,
        sport=sport,
        decision_status="ELIGIBLE",
        scheduling_eligible=True,
        terminal_calls=10,
        failure_rate=0.0,
        zero_consumption_refusal_rate=0.0,
        policy_fingerprint="b" * 64,
        snapshot_fingerprint="c" * 64,
        reason_codes=(),
        decision_fingerprint=decision_char * 64,
    )


def prepared(tmp_path, *, sport="tennis"):
    path = tmp_path / "runtime.db"

    health_ledger = SQLiteProviderHealthEvidenceLedger(path)
    scheduling_ledger = SQLiteProviderSchedulingEvidenceLedger(path)

    decision = health_decision(sport=sport)
    health_ledger.record_decision(decision)

    queue = manifest(
        item(sport=sport),
        sport=sport,
    )

    authorization = authorize_provider_scheduling(
        queue_manifest=queue,
        health_decisions={"P1": decision},
        expected_sport=sport,
    )

    scheduling_ledger.record_authorization(
        authorization=authorization,
        health_evidence_ledger=health_ledger,
    )

    return (
        queue,
        authorization,
        scheduling_ledger,
        health_ledger,
    )


def test_valid_durable_authorization_produces_execution_permit(
    tmp_path,
):
    queue, authorization, scheduling, health = prepared(tmp_path)

    permit = verify_provider_execution_authorization(
        queue_manifest=queue,
        authorization_fingerprint=(
            authorization.authorization_fingerprint
        ),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
        expected_sport="tennis",
    )

    assert permit.sport == "tennis"
    assert permit.queue_fingerprint == authorization.queue_fingerprint
    assert permit.provider_keys == ("P1",)
    assert len(permit.permit_fingerprint) == 64


def test_executor_is_called_only_after_authorization_passes(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)
        return "EXECUTED"

    result = execute_with_provider_authorization(
        queue_manifest=queue,
        authorization_fingerprint=(
            authorization.authorization_fingerprint
        ),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
        executor=executor,
        executor_kwargs={"example": 1},
        expected_sport="tennis",
    )

    assert result == "EXECUTED"
    assert len(calls) == 1
    assert calls[0]["queue_manifest"] == queue


def test_missing_authorization_blocks_before_executor(tmp_path):
    path = tmp_path / "runtime.db"
    scheduling = SQLiteProviderSchedulingEvidenceLedger(path)
    health = SQLiteProviderHealthEvidenceLedger(path)
    calls = []

    def executor(**kwargs):
        calls.append(kwargs)

    with pytest.raises(
        ValueError,
        match="MISSING_DURABLE_SCHEDULING_AUTHORIZATION",
    ):
        execute_with_provider_authorization(
            queue_manifest=manifest(item()),
            authorization_fingerprint="f" * 64,
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            executor=executor,
            executor_kwargs={},
            expected_sport="tennis",
        )

    assert calls == []


def test_different_queue_cannot_reuse_authorization(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)

    changed_queue = manifest(item(char="2"))

    with pytest.raises(
        ValueError,
        match="SCHEDULING_QUEUE_FINGERPRINT_MISMATCH",
    ):
        verify_provider_execution_authorization(
            queue_manifest=changed_queue,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            expected_sport="tennis",
        )


def test_queue_order_change_cannot_reuse_authorization(tmp_path):
    path = tmp_path / "runtime.db"
    health = SQLiteProviderHealthEvidenceLedger(path)
    scheduling = SQLiteProviderSchedulingEvidenceLedger(path)

    decision = health_decision()
    health.record_decision(decision)

    original = manifest(
        item(char="1"),
        item(char="2"),
    )
    authorization = authorize_provider_scheduling(
        queue_manifest=original,
        health_decisions={"P1": decision},
        expected_sport="tennis",
    )
    scheduling.record_authorization(
        authorization=authorization,
        health_evidence_ledger=health,
    )

    reordered = manifest(
        item(char="2"),
        item(char="1"),
    )

    with pytest.raises(
        ValueError,
        match="SCHEDULING_QUEUE_FINGERPRINT_MISMATCH",
    ):
        verify_provider_execution_authorization(
            queue_manifest=reordered,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            expected_sport="tennis",
        )


def test_cross_sport_execution_is_rejected(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        verify_provider_execution_authorization(
            queue_manifest=queue,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            expected_sport="football",
        )


def test_scheduling_evidence_tampering_blocks_execution(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)
    path = tmp_path / "runtime.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE provider_scheduling_evidence
            SET payload_json = ?
            WHERE authorization_fingerprint = ?
            """,
            (
                '{"tampered":true}\n',
                authorization.authorization_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="SCHEDULING_EVIDENCE_INTEGRITY_FAILED",
    ):
        verify_provider_execution_authorization(
            queue_manifest=queue,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            expected_sport="tennis",
        )


def test_health_evidence_tampering_blocks_execution(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)
    path = tmp_path / "runtime.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE provider_health_evidence
            SET payload_json = ?
            WHERE decision_fingerprint = ?
            """,
            ('{"tampered":true}\n', "d" * 64),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="HEALTH_EVIDENCE_INTEGRITY_FAILED",
    ):
        verify_provider_execution_authorization(
            queue_manifest=queue,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            expected_sport="tennis",
        )


def test_executor_cannot_receive_different_queue(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)

    with pytest.raises(
        ValueError,
        match="EXECUTOR_QUEUE_MANIFEST_MISMATCH",
    ):
        execute_with_provider_authorization(
            queue_manifest=queue,
            authorization_fingerprint=(
                authorization.authorization_fingerprint
            ),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
            executor=lambda **kwargs: kwargs,
            executor_kwargs={
                "queue_manifest": manifest(item(char="9"))
            },
            expected_sport="tennis",
        )


def test_execution_permit_fingerprint_is_deterministic(tmp_path):
    queue, authorization, scheduling, health = prepared(tmp_path)

    first = verify_provider_execution_authorization(
        queue_manifest=queue,
        authorization_fingerprint=(
            authorization.authorization_fingerprint
        ),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
        expected_sport="tennis",
    )
    second = verify_provider_execution_authorization(
        queue_manifest=queue,
        authorization_fingerprint=(
            authorization.authorization_fingerprint
        ),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
        expected_sport="tennis",
    )

    assert first.permit_fingerprint == second.permit_fingerprint


def test_execution_permit_keeps_all_automatic_actions_disabled(
    tmp_path,
):
    queue, authorization, scheduling, health = prepared(tmp_path)

    permit = verify_provider_execution_authorization(
        queue_manifest=queue,
        authorization_fingerprint=(
            authorization.authorization_fingerprint
        ),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
        expected_sport="tennis",
    )

    payload = permit.payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
