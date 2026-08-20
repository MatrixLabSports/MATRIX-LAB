from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Mapping, Sequence

from app.core.dataset_manifest import DatasetRowEvidence


WINDOWS = (5, 10, 20, 30, 50)
_ALLOWED_SPORTS = {"football", "tennis"}


@dataclass(frozen=True)
class HistoricalCoverageObservation:
    sport: str
    subject_key: str
    event_key: str
    row_evidence: DatasetRowEvidence
    deep_ready: bool
    core_stats_present: int
    core_stats_total: int

    def __post_init__(self) -> None:
        if self.sport not in _ALLOWED_SPORTS:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if not isinstance(self.subject_key, str) or not self.subject_key.strip():
            raise ValueError("MISSING_SUBJECT_KEY")

        if not isinstance(self.event_key, str) or not self.event_key.strip():
            raise ValueError("MISSING_EVENT_KEY")

        if self.row_evidence.sport != self.sport:
            raise ValueError("CROSS_SPORT_ROW_EVIDENCE")

        if (
            isinstance(self.core_stats_present, bool)
            or isinstance(self.core_stats_total, bool)
            or not isinstance(self.core_stats_present, int)
            or not isinstance(self.core_stats_total, int)
        ):
            raise ValueError("INVALID_CORE_STATS_COVERAGE")

        if self.core_stats_present < 0 or self.core_stats_total < 0:
            raise ValueError("NEGATIVE_CORE_STATS_COVERAGE")

        if self.core_stats_present > self.core_stats_total:
            raise ValueError("PRESENT_EXCEEDS_TOTAL")

    @property
    def admitted(self) -> bool:
        evidence = self.row_evidence.admission_evidence
        return (
            evidence.admission_status == "ADMIT"
            and evidence.model_eligible is True
        )

    @property
    def coverage_ratio(self) -> float | None:
        if self.core_stats_total == 0:
            return None
        return self.core_stats_present / self.core_stats_total

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        if self.admitted:
            return ()

        codes = self.row_evidence.admission_evidence.normalized_reason_codes
        if codes:
            return codes

        return ("UNSPECIFIED_BLOCK",)


def _window_status(valid_count: int, requested: int) -> str:
    if valid_count >= requested:
        return "READY"

    watch_threshold = ceil(requested / 2)
    if valid_count >= watch_threshold:
        return "WATCH"

    return "BLOCK"


def build_coverage_ledger(
    *,
    sport: str,
    subject_key: str,
    observations: Sequence[HistoricalCoverageObservation],
) -> Mapping[str, Any]:
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if not isinstance(subject_key, str) or not subject_key.strip():
        raise ValueError("MISSING_SUBJECT_KEY")

    same_subject = [
        observation
        for observation in observations
        if observation.subject_key == subject_key
    ]

    if any(observation.sport != sport for observation in same_subject):
        raise ValueError("CROSS_SPORT_SUBJECT_COLLISION")

    scoped = [
        observation
        for observation in same_subject
        if observation.sport == sport
    ]

    event_keys = [observation.event_key for observation in scoped]
    if len(event_keys) != len(set(event_keys)):
        raise ValueError("DUPLICATE_EVENT_KEY")

    eligible = [
        observation
        for observation in scoped
        if observation.admitted
    ]

    blocked = [
        observation
        for observation in scoped
        if not observation.admitted
    ]

    deep_ready = [
        observation
        for observation in eligible
        if observation.deep_ready is True
    ]

    ratios = [
        observation.coverage_ratio
        for observation in eligible
        if observation.coverage_ratio is not None
    ]

    average_core_stat_coverage = (
        None
        if not ratios
        else sum(ratios) / len(ratios)
    )

    window_status = {}
    for requested in WINDOWS:
        window_status[str(requested)] = {
            "requested": requested,
            "eligible_count": min(len(eligible), requested),
            "deep_ready_count": min(len(deep_ready), requested),
            "missing_slots": max(0, requested - len(eligible)),
            "status": _window_status(len(eligible), requested),
        }

    blocker_counts: dict[str, int] = {}
    for observation in blocked:
        for code in observation.blocker_codes:
            blocker_counts[code] = blocker_counts.get(code, 0) + 1

    return {
        "schema": "matrix.historical-coverage-ledger/1",
        "sport": sport,
        "subject_key": subject_key.strip(),
        "total_observations": len(scoped),
        "eligible_observations": len(eligible),
        "deep_ready_observations": len(deep_ready),
        "blocked_observations": len(blocked),
        "average_core_stat_coverage": average_core_stat_coverage,
        "window_status": window_status,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }
