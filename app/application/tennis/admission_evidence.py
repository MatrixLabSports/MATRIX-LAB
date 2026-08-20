from __future__ import annotations

from datetime import datetime

from app.core.admission_fingerprint import AdmissionEvidence
from app.application.tennis.point_in_time_admission import (
    TennisAdmissionDecision,
)


def build_tennis_admission_evidence(
    *,
    match_key: str,
    cutoff: datetime,
    known_at: datetime,
    source_status: str,
    source_fingerprint: str,
    decision: TennisAdmissionDecision,
) -> AdmissionEvidence:
    return AdmissionEvidence(
        sport="tennis",
        entity_key=match_key,
        cutoff=cutoff,
        known_at=known_at,
        source_status=source_status,
        admission_status=decision.admission_status,
        model_eligible=decision.model_eligible,
        reason_codes=decision.reason_codes,
        source_fingerprint=source_fingerprint,
        policy_version="P50-TENNIS/1",
    )
