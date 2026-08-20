from datetime import datetime, timezone

import pytest

from app.application.football.admission_evidence import (
    build_football_admission_evidence,
)
from app.application.football.point_in_time_admission import (
    evaluate_football_admission,
)
from app.application.tennis.admission_evidence import (
    build_tennis_admission_evidence,
)
from app.application.tennis.point_in_time_admission import (
    evaluate_tennis_admission,
)
from app.core.admission_fingerprint import AdmissionEvidence


UTC = timezone.utc
CUTOFF = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
KNOWN_AT = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
SOURCE_FP = "a" * 64


def football_decision():
    return evaluate_football_admission(
        fixture_key="F:1",
        kickoff=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        match_finished=True,
    )


def tennis_decision():
    return evaluate_tennis_admission(
        match_key="T:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )


def test_football_decision_fingerprint_is_deterministic():
    a = build_football_admission_evidence(
        fixture_key="F:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=football_decision(),
    )
    b = build_football_admission_evidence(
        fixture_key="F:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=football_decision(),
    )

    assert a.decision_fingerprint == b.decision_fingerprint
    assert len(a.decision_fingerprint) == 64


def test_tennis_decision_fingerprint_is_deterministic():
    a = build_tennis_admission_evidence(
        match_key="T:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=tennis_decision(),
    )
    b = build_tennis_admission_evidence(
        match_key="T:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=tennis_decision(),
    )

    assert a.decision_fingerprint == b.decision_fingerprint


def test_cross_sport_fingerprints_are_distinct():
    football = build_football_admission_evidence(
        fixture_key="X",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=football_decision(),
    )
    tennis = build_tennis_admission_evidence(
        match_key="X",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=tennis_decision(),
    )

    assert football.decision_fingerprint != tennis.decision_fingerprint


def test_source_fingerprint_change_changes_decision_fingerprint():
    a = build_football_admission_evidence(
        fixture_key="F:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint="a" * 64,
        decision=football_decision(),
    )
    b = build_football_admission_evidence(
        fixture_key="F:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint="b" * 64,
        decision=football_decision(),
    )

    assert a.decision_fingerprint != b.decision_fingerprint


def test_reason_code_order_is_canonical():
    a = AdmissionEvidence(
        sport="tennis",
        entity_key="T:CANON",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="BLOCK",
        admission_status="BLOCK",
        model_eligible=False,
        reason_codes=("B_REASON", "A_REASON"),
        source_fingerprint=SOURCE_FP,
    )
    b = AdmissionEvidence(
        sport="tennis",
        entity_key="T:CANON",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="BLOCK",
        admission_status="BLOCK",
        model_eligible=False,
        reason_codes=("A_REASON", "B_REASON"),
        source_fingerprint=SOURCE_FP,
    )

    assert a.decision_fingerprint == b.decision_fingerprint


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="TIMEZONE_UNVERIFIED"):
        AdmissionEvidence(
            sport="football",
            entity_key="F:NAIVE",
            cutoff=datetime(2026, 8, 20, 12, 0),
            known_at=KNOWN_AT,
            source_status="PASS",
            admission_status="ADMIT",
            model_eligible=True,
            reason_codes=(),
            source_fingerprint=SOURCE_FP,
        )


def test_invalid_source_sha_is_rejected():
    with pytest.raises(ValueError, match="SOURCE_FINGERPRINT_MUST_BE_SHA256"):
        AdmissionEvidence(
            sport="football",
            entity_key="F:SHA",
            cutoff=CUTOFF,
            known_at=KNOWN_AT,
            source_status="PASS",
            admission_status="ADMIT",
            model_eligible=True,
            reason_codes=(),
            source_fingerprint="not-a-sha",
        )


def test_future_knowledge_cannot_be_marked_admit():
    future = datetime(2026, 8, 20, 12, 0, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="FUTURE_KNOWLEDGE_MUST_BLOCK"):
        AdmissionEvidence(
            sport="tennis",
            entity_key="T:FUTURE",
            cutoff=CUTOFF,
            known_at=future,
            source_status="PASS",
            admission_status="ADMIT",
            model_eligible=True,
            reason_codes=(),
            source_fingerprint=SOURCE_FP,
        )


def test_safety_flags_are_always_false():
    evidence = build_tennis_admission_evidence(
        match_key="T:1",
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=SOURCE_FP,
        decision=tennis_decision(),
    )

    payload = evidence.payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
