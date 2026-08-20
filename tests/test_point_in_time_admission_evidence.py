from dataclasses import replace
from datetime import datetime, timezone
import sqlite3

import pytest

from app.application.football.point_in_time_admission_evidence import (
    record_football_point_in_time_admission,
)
from app.application.tennis.point_in_time_admission_evidence import (
    record_tennis_point_in_time_admission,
)
from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.point_in_time_admission_evidence import (
    SQLitePointInTimeAdmissionEvidenceLedger,
)
from app.core.point_in_time_data_contract import (
    evaluate_point_in_time_record,
    build_point_in_time_record,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc


def admitted_decision(tmp_path):
    path = tmp_path / "data.db"

    registry = SQLiteCanonicalIdentityRegistry(path)
    entity = registry.build_entity(
        sport="tennis",
        entity_type="player",
        canonical_key="PLAYER:ATP:200",
        display_name="Jugador 200",
    )
    registry.register(entity)

    mappings = SQLiteProviderIdentityMappingLedger(
        path,
        identity_registry=registry,
    )
    mappings.append(
        mappings.build_mapping(
            sport="tennis",
            entity_type="player",
            provider_key="provider-a",
            provider_entity_id="p200",
            canonical_id=entity.canonical_id,
            resolution_method="provider_stable_id",
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 2, tzinfo=UTC),
        )
    )

    record = build_point_in_time_record(
        sport="tennis",
        entity_type="player",
        canonical_id=entity.canonical_id,
        provider_key="provider-a",
        provider_entity_id="p200",
        source_record_id="r200",
        schema_name="tennis.player.stats",
        schema_version="1",
        transformation_version="raw-v1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        payload={"aces": 4},
    )

    decision = evaluate_point_in_time_record(
        record=record,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        identity_registry=registry,
        mapping_ledger=mappings,
    )

    return path, decision


def test_admit_is_persisted_durably(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)

    evidence = record_tennis_point_in_time_admission(
        decision=decision,
        ledger=ledger,
    )

    stored = ledger.get_by_decision_fingerprint(
        decision.decision_fingerprint
    )

    assert evidence.downstream_eligible is True
    assert stored["decision_status"] == "ADMIT"
    assert stored["sport"] == "tennis"
    assert ledger.audit_integrity().ok is True


def test_quarantine_is_persisted_durably(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)

    quarantine = replace(
        decision,
        decision_status="QUARANTINE",
        downstream_eligible=False,
        reason_codes=("SYNTHETIC",),
    )

    from app.core.point_in_time_data_contract import (
        compute_point_in_time_admission_decision_fingerprint,
    )

    quarantine = replace(
        quarantine,
        decision_fingerprint=(
            compute_point_in_time_admission_decision_fingerprint(
                sport=quarantine.sport,
                canonical_id=quarantine.canonical_id,
                decision_status=quarantine.decision_status,
                downstream_eligible=(
                    quarantine.downstream_eligible
                ),
                as_of=quarantine.as_of,
                record_fingerprint=(
                    quarantine.record_fingerprint
                ),
                mapping_fingerprint=(
                    quarantine.mapping_fingerprint
                ),
                reason_codes=quarantine.reason_codes,
            )
        ),
    )

    evidence = ledger.record_decision(quarantine)

    assert evidence.decision_status == "QUARANTINE"
    assert evidence.downstream_eligible is False


def test_exact_replay_is_idempotent(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)

    first = ledger.record_decision(decision)
    second = ledger.record_decision(decision)

    assert first.evidence_id == second.evidence_id
    assert ledger.audit_integrity().records == 1


def test_forged_decision_fingerprint_is_rejected(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)

    forged = replace(
        decision,
        decision_fingerprint="0" * 64,
    )

    with pytest.raises(
        ValueError,
        match="POINT_IN_TIME_DECISION_DERIVATION_MISMATCH",
    ):
        ledger.record_decision(forged)


def test_tampering_is_detected(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)
    ledger.record_decision(decision)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE point_in_time_admission_evidence
            SET payload_json = ?
            WHERE decision_fingerprint = ?
            """,
            (
                '{"tampered":true}\n',
                decision.decision_fingerprint,
            ),
        )
        connection.commit()

    report = ledger.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_football_adapter_rejects_tennis_decision(tmp_path):
    path, decision = admitted_decision(tmp_path)
    ledger = SQLitePointInTimeAdmissionEvidenceLedger(path)

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        record_football_point_in_time_admission(
            decision=decision,
            ledger=ledger,
        )
