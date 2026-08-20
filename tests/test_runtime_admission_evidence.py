from dataclasses import replace
import sqlite3

import pytest

from app.application.football.runtime_admission_evidence import (
    record_football_runtime_admission,
)
from app.application.tennis.runtime_admission_evidence import (
    record_tennis_runtime_admission,
)
from app.core.runtime_admission_evidence import (
    SQLiteRuntimeAdmissionEvidenceLedger,
)
from app.core.runtime_admission_gate import RuntimeAdmissionDecision


def decision(
    *,
    sport="tennis",
    status="ADMIT",
    eligible=True,
    run_char="1",
    decision_char="2",
    reconciliation_char="3",
):
    return RuntimeAdmissionDecision(
        run_id=run_char * 64,
        sport=sport,
        admission_status=status,
        downstream_eligible=eligible,
        processed=1,
        skipped_completed=0,
        recovered_without_fetch=0,
        failed=0,
        reconciliation_fingerprint=reconciliation_char * 64,
        reason_codes=(),
        decision_fingerprint=decision_char * 64,
    )


def test_admit_decision_is_persisted(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )

    evidence = record_tennis_runtime_admission(
        decision=decision(),
        ledger=ledger,
    )

    stored = ledger.get_by_run_id("1" * 64)

    assert len(evidence.evidence_id) == 64
    assert stored["admission_status"] == "ADMIT"
    assert stored["downstream_eligible"] is True
    assert ledger.audit_integrity().ok is True


def test_quarantine_decision_is_persisted(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )

    quarantined = decision(
        status="QUARANTINE",
        eligible=False,
        run_char="4",
        decision_char="5",
        reconciliation_char="6",
    )

    evidence = record_tennis_runtime_admission(
        decision=quarantined,
        ledger=ledger,
    )

    assert evidence.admission_status == "QUARANTINE"
    assert evidence.downstream_eligible is False


def test_exact_replay_is_idempotent(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )
    value = decision()

    first = ledger.record_decision(value)
    second = ledger.record_decision(value)

    assert first.evidence_id == second.evidence_id
    assert ledger.audit_integrity().records == 1


def test_same_run_cannot_mutate_admission_decision(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )
    original = decision()
    ledger.record_decision(original)

    mutated = replace(
        original,
        admission_status="QUARANTINE",
        downstream_eligible=False,
        decision_fingerprint="7" * 64,
        reason_codes=("SYNTHETIC",),
    )

    with pytest.raises(
        ValueError,
        match="RUNTIME_ADMISSION_MUTATION_VIOLATION",
    ):
        ledger.record_decision(mutated)


def test_admit_must_be_downstream_eligible(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(
        ValueError,
        match="ADMISSION_ELIGIBILITY_MISMATCH",
    ):
        ledger.record_decision(
            decision(status="ADMIT", eligible=False)
        )


def test_tennis_adapter_rejects_football_decision(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        record_tennis_runtime_admission(
            decision=decision(sport="football"),
            ledger=ledger,
        )


def test_football_adapter_rejects_tennis_decision(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        record_football_runtime_admission(
            decision=decision(sport="tennis"),
            ledger=ledger,
        )


def test_integrity_audit_detects_payload_tampering(tmp_path):
    path = tmp_path / "runtime.db"
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(path)
    ledger.record_decision(decision())

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE runtime_admission_evidence
            SET payload_json = ?
            WHERE run_id = ?
            """,
            ('{"tampered":true}\n', "1" * 64),
        )
        connection.commit()

    report = ledger.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_evidence_id_is_deterministic(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )
    value = decision()

    first = ledger.evidence_id_for(value)
    second = ledger.evidence_id_for(value)

    assert first == second
    assert len(first) == 64


def test_persisted_payload_keeps_safety_flags_false(tmp_path):
    ledger = SQLiteRuntimeAdmissionEvidenceLedger(
        tmp_path / "runtime.db"
    )
    ledger.record_decision(decision())

    payload = ledger.get_by_run_id("1" * 64)

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
