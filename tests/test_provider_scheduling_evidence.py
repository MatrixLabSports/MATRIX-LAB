from dataclasses import replace
import sqlite3

import pytest

from app.application.football.provider_scheduling_evidence import (
    record_football_provider_scheduling_authorization,
)
from app.application.tennis.provider_scheduling_evidence import (
    record_tennis_provider_scheduling_authorization,
)
from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_health_policy import ProviderHealthDecision
from app.core.provider_scheduling_authorization import (
    ProviderSchedulingAuthorization,
)
from app.core.provider_scheduling_evidence import (
    SQLiteProviderSchedulingEvidenceLedger,
)


def health_decision(
    *,
    provider_key="P1",
    sport="tennis",
    status="ELIGIBLE",
    eligible=True,
    decision_char="d",
):
    return ProviderHealthDecision(
        provider_key=provider_key,
        sport=sport,
        decision_status=status,
        scheduling_eligible=eligible,
        terminal_calls=10,
        failure_rate=0.0,
        zero_consumption_refusal_rate=0.0,
        policy_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
        reason_codes=(),
        decision_fingerprint=decision_char * 64,
    )


def authorization(
    *,
    sport="tennis",
    status="AUTHORIZED",
    eligible=True,
    queue_char="1",
    auth_char="2",
    provider_keys=("P1",),
    decision_fingerprints=("d" * 64,),
):
    return ProviderSchedulingAuthorization(
        sport=sport,
        authorization_status=status,
        execution_eligible=eligible,
        queue_fingerprint=queue_char * 64,
        queue_item_fingerprints=(
            ("3" * 64,) if provider_keys else ()
        ),
        provider_keys=provider_keys,
        eligible_provider_keys=(
            provider_keys if eligible and status == "AUTHORIZED" else ()
        ),
        blocked_provider_keys=(
            provider_keys if status == "BLOCKED" else ()
        ),
        missing_provider_keys=(),
        decision_fingerprints=decision_fingerprints,
        reason_codes=(
            () if status != "BLOCKED"
            else ("PROVIDER_NOT_ELIGIBLE:P1",)
        ),
        authorization_fingerprint=auth_char * 64,
    )


def ledgers(tmp_path):
    path = tmp_path / "runtime.db"
    return (
        SQLiteProviderSchedulingEvidenceLedger(path),
        SQLiteProviderHealthEvidenceLedger(path),
    )


def persist_health(health_ledger, **kwargs):
    value = health_decision(**kwargs)
    health_ledger.record_decision(value)
    return value


def test_authorized_queue_requires_and_persists_durable_health_evidence(
    tmp_path,
):
    scheduling, health = ledgers(tmp_path)
    persist_health(health)

    evidence = record_tennis_provider_scheduling_authorization(
        authorization=authorization(),
        scheduling_evidence_ledger=scheduling,
        health_evidence_ledger=health,
    )

    stored = scheduling.get_by_authorization_fingerprint("2" * 64)

    assert len(evidence.evidence_id) == 64
    assert evidence.queue_fingerprint == "1" * 64
    assert stored["queue_fingerprint"] == "1" * 64
    assert stored["decision_fingerprints"] == ["d" * 64]
    assert scheduling.audit_integrity().ok is True


def test_authorized_queue_without_durable_health_evidence_fails_closed(
    tmp_path,
):
    scheduling, health = ledgers(tmp_path)

    with pytest.raises(
        ValueError,
        match="MISSING_DURABLE_HEALTH_EVIDENCE",
    ):
        scheduling.record_authorization(
            authorization=authorization(),
            health_evidence_ledger=health,
        )


def test_authorized_queue_rejects_noneligible_durable_health(
    tmp_path,
):
    scheduling, health = ledgers(tmp_path)
    persist_health(
        health,
        status="INELIGIBLE",
        eligible=False,
    )

    with pytest.raises(
        ValueError,
        match="AUTHORIZED_PROVIDER_NOT_ELIGIBLE",
    ):
        scheduling.record_authorization(
            authorization=authorization(),
            health_evidence_ledger=health,
        )


def test_cross_sport_health_evidence_fails_closed(tmp_path):
    scheduling, health = ledgers(tmp_path)
    persist_health(
        health,
        sport="football",
    )

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        scheduling.record_authorization(
            authorization=authorization(),
            health_evidence_ledger=health,
        )


def test_exact_replay_is_idempotent(tmp_path):
    scheduling, health = ledgers(tmp_path)
    persist_health(health)
    value = authorization()

    first = scheduling.record_authorization(
        authorization=value,
        health_evidence_ledger=health,
    )
    second = scheduling.record_authorization(
        authorization=value,
        health_evidence_ledger=health,
    )

    assert first.evidence_id == second.evidence_id
    assert scheduling.audit_integrity().records == 1


def test_same_authorization_fingerprint_cannot_mutate(tmp_path):
    scheduling, health = ledgers(tmp_path)
    persist_health(health)
    original = authorization()

    scheduling.record_authorization(
        authorization=original,
        health_evidence_ledger=health,
    )

    mutated = replace(
        original,
        queue_fingerprint="9" * 64,
    )

    with pytest.raises(
        ValueError,
        match="PROVIDER_SCHEDULING_MUTATION_VIOLATION",
    ):
        scheduling.record_authorization(
            authorization=mutated,
            health_evidence_ledger=health,
        )


def test_blocked_authorization_can_preserve_fail_closed_evidence(
    tmp_path,
):
    scheduling, health = ledgers(tmp_path)

    blocked = authorization(
        status="BLOCKED",
        eligible=False,
        auth_char="4",
        decision_fingerprints=(),
    )

    evidence = scheduling.record_authorization(
        authorization=blocked,
        health_evidence_ledger=health,
    )

    assert evidence.authorization_status == "BLOCKED"
    assert evidence.execution_eligible is False


def test_empty_queue_is_persisted_without_health_decisions(tmp_path):
    scheduling, health = ledgers(tmp_path)

    empty = ProviderSchedulingAuthorization(
        sport="tennis",
        authorization_status="EMPTY_QUEUE",
        execution_eligible=True,
        queue_fingerprint="5" * 64,
        queue_item_fingerprints=(),
        provider_keys=(),
        eligible_provider_keys=(),
        blocked_provider_keys=(),
        missing_provider_keys=(),
        decision_fingerprints=(),
        reason_codes=(),
        authorization_fingerprint="6" * 64,
    )

    evidence = scheduling.record_authorization(
        authorization=empty,
        health_evidence_ledger=health,
    )

    assert evidence.authorization_status == "EMPTY_QUEUE"
    assert evidence.execution_eligible is True


def test_tennis_adapter_rejects_football_authorization(tmp_path):
    scheduling, health = ledgers(tmp_path)

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        record_tennis_provider_scheduling_authorization(
            authorization=authorization(sport="football"),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
        )


def test_football_adapter_rejects_tennis_authorization(tmp_path):
    scheduling, health = ledgers(tmp_path)

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        record_football_provider_scheduling_authorization(
            authorization=authorization(sport="tennis"),
            scheduling_evidence_ledger=scheduling,
            health_evidence_ledger=health,
        )


def test_integrity_audit_detects_queue_payload_tampering(tmp_path):
    path = tmp_path / "runtime.db"
    scheduling = SQLiteProviderSchedulingEvidenceLedger(path)
    health = SQLiteProviderHealthEvidenceLedger(path)
    persist_health(health)

    scheduling.record_authorization(
        authorization=authorization(),
        health_evidence_ledger=health,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE provider_scheduling_evidence
            SET payload_json = ?
            WHERE authorization_fingerprint = ?
            """,
            ('{"tampered":true}\n', "2" * 64),
        )
        connection.commit()

    report = scheduling.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_persisted_payload_keeps_safety_flags_false(tmp_path):
    scheduling, health = ledgers(tmp_path)
    persist_health(health)

    scheduling.record_authorization(
        authorization=authorization(),
        health_evidence_ledger=health,
    )

    payload = scheduling.get_by_authorization_fingerprint("2" * 64)

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
