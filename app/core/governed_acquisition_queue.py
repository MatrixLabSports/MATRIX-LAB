from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping, Sequence

_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_RIGHTS = {"PASS", "RESEARCH_ONLY"}

def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

def _sha256(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()

def _validate_sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("SOURCE_FINGERPRINT_MUST_BE_SHA256")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError("SOURCE_FINGERPRINT_MUST_BE_SHA256") from error

def _validate_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"INVALID_{name.upper()}")

@dataclass(frozen=True)
class AcquisitionCandidate:
    sport: str
    subject_key: str
    provider_key: str
    competition_key: str
    season_key: str
    disposition: str
    priority_score: float
    expected_rows: int
    estimated_request_cost: int
    rights_status: str
    identity_status: str
    chronology_status: str
    provider_status: str
    source_fingerprint: str

    def __post_init__(self) -> None:
        if self.sport not in _ALLOWED_SPORTS:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")
        for name, value in (
            ("subject_key", self.subject_key),
            ("provider_key", self.provider_key),
            ("competition_key", self.competition_key),
            ("season_key", self.season_key),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MISSING_{name.upper()}")
        if self.disposition not in {"PRIORITIZE", "NO_ACTION", "QUARANTINE"}:
            raise ValueError("INVALID_DISPOSITION")
        if (
            isinstance(self.priority_score, bool)
            or not isinstance(self.priority_score, (int, float))
            or not isfinite(float(self.priority_score))
            or self.priority_score < 0
        ):
            raise ValueError("INVALID_PRIORITY_SCORE")
        _validate_non_negative_int("EXPECTED_ROWS", self.expected_rows)
        _validate_non_negative_int("ESTIMATED_REQUEST_COST", self.estimated_request_cost)
        _validate_sha256(self.source_fingerprint)

@dataclass(frozen=True)
class ProviderBudget:
    provider_key: str
    max_requests: int
    max_rows: int

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise ValueError("MISSING_PROVIDER_KEY")
        _validate_non_negative_int("MAX_REQUESTS", self.max_requests)
        _validate_non_negative_int("MAX_ROWS", self.max_rows)

def _hard_blockers(candidate: AcquisitionCandidate) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.rights_status not in _ALLOWED_RIGHTS:
        reasons.append("RIGHTS_NOT_VERIFIED")
    if candidate.identity_status != "PASS":
        reasons.append("IDENTITY_NOT_VERIFIED")
    if candidate.chronology_status != "PASS":
        reasons.append("CHRONOLOGY_NOT_VERIFIED")
    if candidate.provider_status != "PASS":
        reasons.append("PROVIDER_NOT_READY")
    if candidate.disposition != "PRIORITIZE":
        reasons.append("NOT_PRIORITIZED")
    if candidate.expected_rows > 0 and candidate.estimated_request_cost == 0:
        reasons.append("INVALID_ZERO_REQUEST_COST")
    return tuple(sorted(set(reasons)))

def build_bounded_acquisition_queue(
    *,
    sport: str,
    candidates: Sequence[AcquisitionCandidate],
    budgets: Sequence[ProviderBudget],
    queue_limit: int = 100,
) -> Mapping[str, Any]:
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    _validate_non_negative_int("QUEUE_LIMIT", queue_limit)
    if any(candidate.sport != sport for candidate in candidates):
        raise ValueError("CROSS_SPORT_CANDIDATE_CONTAMINATION")

    budget_map: dict[str, ProviderBudget] = {}
    for budget in budgets:
        if budget.provider_key in budget_map:
            raise ValueError("DUPLICATE_PROVIDER_BUDGET")
        budget_map[budget.provider_key] = budget

    eligible: list[tuple[AcquisitionCandidate, float]] = []
    quarantined: list[dict[str, Any]] = []

    for candidate in candidates:
        blockers = _hard_blockers(candidate)
        if blockers:
            quarantined.append({
                "subject_key": candidate.subject_key,
                "provider_key": candidate.provider_key,
                "blockers": blockers,
            })
            continue
        if candidate.provider_key not in budget_map:
            quarantined.append({
                "subject_key": candidate.subject_key,
                "provider_key": candidate.provider_key,
                "blockers": ("MISSING_PROVIDER_BUDGET",),
            })
            continue
        efficiency = candidate.priority_score / max(1, candidate.estimated_request_cost)
        eligible.append((candidate, efficiency))

    eligible.sort(
        key=lambda item: (
            -item[1],
            -item[0].priority_score,
            item[0].provider_key,
            item[0].subject_key,
        )
    )

    used_requests = {key: 0 for key in budget_map}
    used_rows = {key: 0 for key in budget_map}
    queue: list[dict[str, Any]] = []

    for candidate, efficiency in eligible:
        if len(queue) >= queue_limit:
            break

        budget = budget_map[candidate.provider_key]
        next_requests = used_requests[candidate.provider_key] + candidate.estimated_request_cost
        next_rows = used_rows[candidate.provider_key] + candidate.expected_rows

        if next_requests > budget.max_requests:
            quarantined.append({
                "subject_key": candidate.subject_key,
                "provider_key": candidate.provider_key,
                "blockers": ("PROVIDER_REQUEST_BUDGET_EXCEEDED",),
            })
            continue

        if next_rows > budget.max_rows:
            quarantined.append({
                "subject_key": candidate.subject_key,
                "provider_key": candidate.provider_key,
                "blockers": ("PROVIDER_ROW_BUDGET_EXCEEDED",),
            })
            continue

        body = {
            "sport": sport,
            "subject_key": candidate.subject_key,
            "provider_key": candidate.provider_key,
            "competition_key": candidate.competition_key,
            "season_key": candidate.season_key,
            "priority_score": candidate.priority_score,
            "priority_per_request": round(efficiency, 8),
            "expected_rows": candidate.expected_rows,
            "estimated_request_cost": candidate.estimated_request_cost,
            "rights_status": candidate.rights_status,
            "source_fingerprint": candidate.source_fingerprint.lower(),
        }
        queue.append({**body, "queue_item_fingerprint": _sha256(body)})
        used_requests[candidate.provider_key] = next_requests
        used_rows[candidate.provider_key] = next_rows

    manifest = {
        "schema": "matrix.governed-acquisition-queue/1",
        "sport": sport,
        "queue_limit": queue_limit,
        "queue": queue,
        "quarantined": sorted(
            quarantined,
            key=lambda item: (
                item["provider_key"],
                item["subject_key"],
                item["blockers"],
            ),
        ),
        "provider_usage": {
            key: {
                "requests_used": used_requests[key],
                "requests_max": budget_map[key].max_requests,
                "rows_used": used_rows[key],
                "rows_max": budget_map[key].max_rows,
            }
            for key in sorted(budget_map)
        },
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }
    return {**manifest, "queue_fingerprint": _sha256(manifest)}
