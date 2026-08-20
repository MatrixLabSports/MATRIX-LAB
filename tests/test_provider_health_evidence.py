from dataclasses import replace
import sqlite3

import pytest

from app.application.football.provider_health_evidence import (
    record_football_provider_health_decision,
)
from app.application.tennis.provider_health_evidence import (
    record_tennis_provider_health_decision,
)
from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_health_policy import ProviderHealthDecision


def decision(
    *,
    sport="tennis",
    provider_key="P1",
    status="ELIGIBLE",
    eligible=True,
    snapshot_char="1",
    policy_char="2",
    decision_char="3",
):
    return ProviderHealthDecision(
        provider_key=provider_key,
        sport=sport,
        decision_status=status,
        scheduling_eligible=eligible,
        terminal_calls=10,
        failure_rate=0.1,
        zero_consumption_refusal_rate=0.0,
        policy_fingerprint=policy_char * 64,
        snapshot_fingerprint=snapshot_char * 64,
        reason_codes=(),
        decision_fingerprint=decision_char * 64,
    )


def test_eligible_decision_is_persisted(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    evidence = record_tennis_provider_health_decision(
        decision=decision(),
        ledger=ledger,
    )

    stored = ledger.get_by_decision_fingerprint("3" * 64)

    assert len(evidence.evidence_id) == 64
    assert stored["decision_status"] == "ELIGIBLE"
    assert stored["scheduling_eligible"] is True
    assert ledger.audit_integrity().ok is True


def test_review_required_decision_is_persisted(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    value = decision(
        status="REVIEW_REQUIRED",
        eligible=False,
        snapshot_char="4",
        policy_char="5",
        decision_char="6",
    )

    evidence = ledger.record_decision(value)

    assert evidence.decision_status == "REVIEW_REQUIRED"
    assert evidence.scheduling_eligible is False


def test_ineligible_decision_is_persisted(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    value = decision(
        status="INELIGIBLE",
        eligible=False,
        snapshot_char="7",
        policy_char="8",
        decision_char="9",
    )

    evidence = ledger.record_decision(value)

    assert evidence.decision_status == "INELIGIBLE"
    assert evidence.scheduling_eligible is False


def test_exact_replay_is_idempotent(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )
    value = decision()

    first = ledger.record_decision(value)
    second = ledger.record_decision(value)

    assert first.evidence_id == second.evidence_id
    assert ledger.audit_integrity().records == 1


def test_same_snapshot_policy_pair_cannot_mutate(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )
    original = decision()
    ledger.record_decision(original)

    mutated = replace(
        original,
        decision_status="INELIGIBLE",
        scheduling_eligible=False,
        decision_fingerprint="a" * 64,
        reason_codes=("SYNTHETIC",),
    )

    with pytest.raises(
        ValueError,
        match="PROVIDER_HEALTH_MUTATION_VIOLATION",
    ):
        ledger.record_decision(mutated)


def test_eligible_status_requires_scheduling_eligible(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(
        ValueError,
        match="HEALTH_ELIGIBILITY_MISMATCH",
    ):
        ledger.record_decision(
            decision(status="ELIGIBLE", eligible=False)
        )


def test_tennis_adapter_rejects_football_decision(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        record_tennis_provider_health_decision(
            decision=decision(sport="football"),
            ledger=ledger,
        )


def test_football_adapter_rejects_tennis_decision(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        record_football_provider_health_decision(
            decision=decision(sport="tennis"),
            ledger=ledger,
        )


def test_integrity_audit_detects_payload_tampering(tmp_path):
    path = tmp_path / "runtime.db"
    ledger = SQLiteProviderHealthEvidenceLedger(path)
    ledger.record_decision(decision())

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE provider_health_evidence
            SET payload_json = ?
            WHERE decision_fingerprint = ?
            """,
            ('{"tampered":true}\n', "3" * 64),
        )
        connection.commit()

    report = ledger.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_evidence_id_is_deterministic(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )
    value = decision()

    first = ledger.evidence_id_for(value)
    second = ledger.evidence_id_for(value)

    assert first == second
    assert len(first) == 64


def test_persisted_payload_keeps_automatic_switching_disabled(tmp_path):
    ledger = SQLiteProviderHealthEvidenceLedger(
        tmp_path / "runtime.db"
    )
    ledger.record_decision(decision())

    payload = ledger.get_by_decision_fingerprint("3" * 64)

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
