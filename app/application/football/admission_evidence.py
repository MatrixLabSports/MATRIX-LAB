from __future__ import annotations

from datetime import datetime

from app.core.admission_fingerprint import AdmissionEvidence
from app.application.football.point_in_time_admission import (
    FootballAdmissionDecision,
)


def build_football_admission_evidence(
    *,
    fixture_key: str,
    cutoff: datetime,
    known_at: datetime,
    source_status: str,
    source_fingerprint: str,
    decision: FootballAdmissionDecision,
) -> AdmissionEvidence:
    return AdmissionEvidence(
        sport="football",
        entity_key=fixture_key,
        cutoff=cutoff,
        known_at=known_at,
        source_status=source_status,
        admission_status=decision.admission_status,
        model_eligible=decision.model_eligible,
        reason_codes=decision.reason_codes,
        source_fingerprint=source_fingerprint,
        policy_version="P50-FOOTBALL/1",
    )
