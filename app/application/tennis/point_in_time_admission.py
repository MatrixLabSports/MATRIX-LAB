from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TennisAdmissionDecision:
    admission_status: str
    model_eligible: bool
    reason_codes: tuple[str, ...]


def _is_timezone_aware(value: datetime) -> bool:
    return (
        value.tzinfo is not None
        and value.utcoffset() is not None
    )


def evaluate_tennis_admission(
    *,
    match_key: str,
    cutoff: datetime,
    known_at: datetime,
    source_status: str,
    match_finished: bool,
    exact_match_time_verified: bool,
    same_tournament_cutoff_sensitive: bool,
) -> TennisAdmissionDecision:
    if not match_key.strip():
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("MISSING_CANONICAL_MATCH_KEY",),
        )

    if not _is_timezone_aware(cutoff) or not _is_timezone_aware(known_at):
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("TIMEZONE_UNVERIFIED",),
        )

    if known_at > cutoff:
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("KNOWN_AFTER_CUTOFF",),
        )

    if not match_finished:
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("MATCH_NOT_FINISHED",),
        )

    if source_status not in {"PASS", "WATCH", "BLOCK"}:
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("INVALID_SOURCE_STATUS",),
        )

    if source_status == "BLOCK":
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("SOURCE_BLOCK",),
        )

    if source_status == "WATCH":
        return TennisAdmissionDecision(
            admission_status="WATCH",
            model_eligible=False,
            reason_codes=("SOURCE_WATCH_EXCLUDED",),
        )

    if (
        same_tournament_cutoff_sensitive
        and not exact_match_time_verified
    ):
        return TennisAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=(
                "INTRA_TOURNAMENT_CHRONOLOGY_UNVERIFIED",
            ),
        )

    return TennisAdmissionDecision(
        admission_status="ADMIT",
        model_eligible=True,
        reason_codes=(),
    )
