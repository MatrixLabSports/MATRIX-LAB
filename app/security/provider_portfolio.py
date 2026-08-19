from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256
from app.security.provider_operational import (
    ProviderOperationalAssessment,
    ProviderOperationalStatus,
    ProviderRole,
)
from app.security.provider_rights import ProviderRightsAssessment, ProviderRightsStatus


def _required(value: str, name: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"{name} is required")
    return clean


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class PortfolioStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderCandidate:
    provider_id: str
    role: ProviderRole
    rights: ProviderRightsAssessment
    operational: ProviderOperationalAssessment
    independence_group: str
    priority: int

    def __post_init__(self) -> None:
        _required(self.provider_id, "provider_id")
        _required(self.independence_group, "independence_group")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be int")
        if self.priority < 1:
            raise ValueError("priority must be >= 1")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderPortfolioPlan:
    plan_id: str
    sport: str
    market_or_dataset: str
    primary_provider_id: str
    fallback_provider_ids: tuple[str, ...]
    reference_provider_ids: tuple[str, ...]
    created_at: datetime
    human_approved: bool

    def __post_init__(self) -> None:
        _required(self.plan_id, "plan_id")
        _required(self.sport, "sport")
        _required(self.market_or_dataset, "market_or_dataset")
        _required(self.primary_provider_id, "primary_provider_id")
        _aware(self.created_at, "created_at")
        if len(set(self.fallback_provider_ids)) != len(self.fallback_provider_ids):
            raise ValueError("fallback_provider_ids may not contain duplicates")
        if len(set(self.reference_provider_ids)) != len(self.reference_provider_ids):
            raise ValueError("reference_provider_ids may not contain duplicates")
        all_ids = (self.primary_provider_id,) + self.fallback_provider_ids + self.reference_provider_ids
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("provider may not occupy multiple portfolio roles")
        if not self.fallback_provider_ids:
            raise ValueError("at least one fallback provider is required")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderPortfolioAssessment:
    status: PortfolioStatus
    reasons: tuple[str, ...]
    plan_fingerprint: str
    selected_primary: str | None
    failover_ready: bool
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_provider_switch:
            raise ValueError("portfolio gate may not enable automatic provider switching")
        if self.automatic_wagering:
            raise ValueError("portfolio gate may not enable wagering")


def _candidate_map(candidates: Iterable[ProviderCandidate]) -> dict[str, ProviderCandidate]:
    result: dict[str, ProviderCandidate] = {}
    for candidate in candidates:
        if candidate.provider_id in result:
            raise ValueError(f"duplicate provider candidate: {candidate.provider_id}")
        result[candidate.provider_id] = candidate
    return result


def evaluate_provider_portfolio(
    plan: ProviderPortfolioPlan,
    candidates: Iterable[ProviderCandidate],
) -> ProviderPortfolioAssessment:
    candidate_by_id = _candidate_map(candidates)
    reasons: list[str] = []
    watch: list[str] = []

    required_ids = (plan.primary_provider_id,) + plan.fallback_provider_ids + plan.reference_provider_ids
    for provider_id in required_ids:
        if provider_id not in candidate_by_id:
            reasons.append(f"MISSING_PROVIDER_CANDIDATE:{provider_id}")

    primary = candidate_by_id.get(plan.primary_provider_id)
    fallback_candidates = [candidate_by_id.get(pid) for pid in plan.fallback_provider_ids]

    if primary is not None:
        if primary.role is not ProviderRole.PRIMARY:
            reasons.append("PRIMARY_PROVIDER_ROLE_MISMATCH")
        if primary.rights.status is ProviderRightsStatus.BLOCK:
            reasons.append("PRIMARY_PROVIDER_RIGHTS_BLOCK")
        elif primary.rights.status is ProviderRightsStatus.WATCH:
            watch.append("PRIMARY_PROVIDER_RIGHTS_WATCH")
        if primary.operational.status is ProviderOperationalStatus.BLOCK:
            reasons.append("PRIMARY_PROVIDER_OPERATIONAL_BLOCK")
        elif primary.operational.status is ProviderOperationalStatus.WATCH:
            watch.append("PRIMARY_PROVIDER_OPERATIONAL_WATCH")

    healthy_fallbacks: list[ProviderCandidate] = []
    for index, fallback in enumerate(fallback_candidates):
        pid = plan.fallback_provider_ids[index]
        if fallback is None:
            continue
        if fallback.role is not ProviderRole.SECONDARY:
            reasons.append(f"FALLBACK_PROVIDER_ROLE_MISMATCH:{pid}")
            continue
        if fallback.rights.status is ProviderRightsStatus.PASS and fallback.operational.status is ProviderOperationalStatus.PASS:
            healthy_fallbacks.append(fallback)
        elif fallback.rights.status is ProviderRightsStatus.BLOCK or fallback.operational.status is ProviderOperationalStatus.BLOCK:
            watch.append(f"FALLBACK_PROVIDER_NOT_READY:{pid}")
        else:
            watch.append(f"FALLBACK_PROVIDER_WATCH:{pid}")

    for pid in plan.reference_provider_ids:
        reference = candidate_by_id.get(pid)
        if reference is None:
            continue
        if reference.role is not ProviderRole.REFERENCE:
            reasons.append(f"REFERENCE_PROVIDER_ROLE_MISMATCH:{pid}")
        if reference.rights.status is ProviderRightsStatus.BLOCK:
            reasons.append(f"REFERENCE_PROVIDER_RIGHTS_BLOCK:{pid}")
        if reference.operational.status is ProviderOperationalStatus.BLOCK:
            watch.append(f"REFERENCE_PROVIDER_OPERATIONAL_BLOCK:{pid}")

    failover_ready = bool(healthy_fallbacks)
    if not failover_ready:
        reasons.append("NO_HEALTHY_FAILOVER_PROVIDER")

    if primary is not None and healthy_fallbacks:
        if all(f.independence_group == primary.independence_group for f in healthy_fallbacks):
            reasons.append("FAILOVER_NOT_INDEPENDENT_FROM_PRIMARY")

    priorities = [candidate.priority for candidate in candidate_by_id.values()]
    if len(priorities) != len(set(priorities)):
        watch.append("DUPLICATE_PROVIDER_PRIORITIES")

    if not plan.human_approved:
        reasons.append("PORTFOLIO_PLAN_NOT_HUMAN_APPROVED")

    if reasons:
        status = PortfolioStatus.BLOCK
        all_reasons = tuple(dict.fromkeys(reasons + watch))
    elif watch:
        status = PortfolioStatus.WATCH
        all_reasons = tuple(dict.fromkeys(watch))
    else:
        status = PortfolioStatus.PASS
        all_reasons = ()

    return ProviderPortfolioAssessment(
        status=status,
        reasons=all_reasons,
        plan_fingerprint=plan.fingerprint,
        selected_primary=plan.primary_provider_id if primary is not None else None,
        failover_ready=failover_ready,
    )


def choose_failover_candidate(
    plan: ProviderPortfolioPlan,
    candidates: Iterable[ProviderCandidate],
) -> ProviderCandidate | None:
    candidate_by_id = _candidate_map(candidates)
    primary = candidate_by_id.get(plan.primary_provider_id)
    healthy: list[ProviderCandidate] = []
    for pid in plan.fallback_provider_ids:
        candidate = candidate_by_id.get(pid)
        if candidate is None:
            continue
        if candidate.role is not ProviderRole.SECONDARY:
            continue
        if candidate.rights.status is not ProviderRightsStatus.PASS:
            continue
        if candidate.operational.status is not ProviderOperationalStatus.PASS:
            continue
        if primary is not None and candidate.independence_group == primary.independence_group:
            continue
        healthy.append(candidate)
    if not healthy:
        return None
    return sorted(healthy, key=lambda c: (c.priority, c.provider_id))[0]
