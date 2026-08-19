from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256
from app.security.provider_quarantine import ProviderQuarantineRecord
from app.security.provider_reconciliation import (
    ProviderEventSnapshot,
    ReconciliationAssessment,
    ReconciliationPolicy,
    ReconciliationStatus,
    reconcile_snapshots,
)
from app.security.provider_source_of_truth import AuthorityAssessment, AuthorityStatus, TruthDomain


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


class DisagreementStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    QUARANTINE = "QUARANTINE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DisagreementPolicy:
    quarantine_ttl_seconds: int = 300
    require_independent_third_source: bool = True
    allow_authority_for_statistics: bool = True
    allow_authority_for_timing: bool = True

    def __post_init__(self) -> None:
        _positive_int(self.quarantine_ttl_seconds, "quarantine_ttl_seconds")


@dataclass(frozen=True)
class ProviderIndependence:
    provider_id: str
    independence_group: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if not self.independence_group.strip():
            raise ValueError("independence_group is required")


@dataclass(frozen=True)
class DisagreementResolution:
    status: DisagreementStatus
    reasons: tuple[str, ...]
    primary_fingerprint: str
    fallback_fingerprint: str
    third_fingerprint: str | None
    selected_evidence_fingerprint: str | None
    reconciliation_fingerprints: tuple[str, ...]
    quarantine_required: bool
    resolved_by: str | None
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_provider_switch:
            raise ValueError("disagreement resolution may not switch providers automatically")
        if self.automatic_model_promotion:
            raise ValueError("disagreement resolution may not promote models")
        if self.automatic_wagering:
            raise ValueError("disagreement resolution may not enable wagering")
        if self.status is DisagreementStatus.QUARANTINE and not self.quarantine_required:
            raise ValueError("QUARANTINE status requires quarantine_required")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


_IDENTITY_PREFIXES = (
    "SPORT_MISMATCH",
    "CANONICAL_FIXTURE_MISMATCH",
    "COMPETITION_MISMATCH",
    "HOME_ENTITY_MISMATCH",
    "AWAY_ENTITY_MISMATCH",
    "KICKOFF_MISMATCH",
)
_TIMING_REASONS = {
    "PRIMARY_SNAPSHOT_FROM_FUTURE",
    "FALLBACK_SNAPSHOT_FROM_FUTURE",
    "PRIMARY_SNAPSHOT_STALE",
    "FALLBACK_SNAPSHOT_STALE",
    "OBSERVATION_SKEW_EXCEEDED",
    "EVENT_TIME_SKEW_EXCEEDED",
}
_STATE_REASONS = {"TERMINAL_EVENT_STATE_MISMATCH", "EVENT_STATE_MISMATCH"}
_SCORE_REASONS = {"SCORE_MISMATCH"}


def _domain_for_reason(reason: str) -> TruthDomain | None:
    if reason.startswith(_IDENTITY_PREFIXES):
        return TruthDomain.FIXTURE_IDENTITY
    if reason in _TIMING_REASONS:
        return TruthDomain.TIMING
    if reason in _STATE_REASONS:
        return TruthDomain.EVENT_STATE
    if reason in _SCORE_REASONS:
        return TruthDomain.SCORE
    if reason.startswith("STAT_DELTA_EXCEEDED:") or reason.startswith("MISSING_REQUIRED_STAT:"):
        return TruthDomain.STATISTICS
    if "MISSING_REQUIRED_MARKET:" in reason:
        return TruthDomain.MARKET_IDENTITY
    if reason == "PROVIDERS_MUST_DIFFER":
        return TruthDomain.FIXTURE_IDENTITY
    return None


def _blocking_domains(assessment: ReconciliationAssessment) -> set[TruthDomain]:
    if assessment.status is not ReconciliationStatus.BLOCK:
        return set()
    return {domain for reason in assessment.reasons if (domain := _domain_for_reason(reason)) is not None}


def _authority_can_resolve(
    authority: AuthorityAssessment | None,
    domains: set[TruthDomain],
    policy: DisagreementPolicy,
    primary: ProviderEventSnapshot,
    fallback: ProviderEventSnapshot,
) -> ProviderEventSnapshot | None:
    if authority is None or authority.status is not AuthorityStatus.PASS or authority.provider_id is None:
        return None
    if len(domains) != 1 or authority.domain not in domains:
        return None
    if authority.domain is TruthDomain.STATISTICS and not policy.allow_authority_for_statistics:
        return None
    if authority.domain is TruthDomain.TIMING and not policy.allow_authority_for_timing:
        return None
    if authority.domain not in {TruthDomain.STATISTICS, TruthDomain.TIMING}:
        return None
    if authority.provider_id == primary.provider_id:
        return primary
    if authority.provider_id == fallback.provider_id:
        return fallback
    return None


def _independence_map(values: tuple[ProviderIndependence, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if item.provider_id in result:
            raise ValueError(f"duplicate provider independence: {item.provider_id}")
        result[item.provider_id] = item.independence_group
    return result


def resolve_provider_disagreement(
    primary: ProviderEventSnapshot,
    fallback: ProviderEventSnapshot,
    reconciliation_policy: ReconciliationPolicy,
    disagreement_policy: DisagreementPolicy,
    *,
    now: datetime,
    third: ProviderEventSnapshot | None = None,
    independence: tuple[ProviderIndependence, ...] = (),
    authority: AuthorityAssessment | None = None,
) -> DisagreementResolution:
    _aware(now, "now")
    base = reconcile_snapshots(primary, fallback, reconciliation_policy, now=now)
    reconciliations = [base.fingerprint]

    if base.status is ReconciliationStatus.PASS:
        return DisagreementResolution(
            DisagreementStatus.PASS,
            (),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint if third is not None else None,
            primary.fingerprint,
            tuple(reconciliations),
            False,
            "PAIR_RECONCILIATION",
        )
    if base.status is ReconciliationStatus.WATCH:
        return DisagreementResolution(
            DisagreementStatus.WATCH,
            base.reasons,
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint if third is not None else None,
            None,
            tuple(reconciliations),
            False,
            "PAIR_RECONCILIATION_WITH_TOLERANCE",
        )

    domains = _blocking_domains(base)
    selected = _authority_can_resolve(authority, domains, disagreement_policy, primary, fallback)
    if selected is not None:
        return DisagreementResolution(
            DisagreementStatus.WATCH,
            tuple(dict.fromkeys(base.reasons + ("RESOLVED_BY_GOVERNED_SOURCE_OF_TRUTH",))),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint if third is not None else None,
            selected.fingerprint,
            tuple(reconciliations),
            False,
            "GOVERNED_SOURCE_OF_TRUTH",
        )

    # Identity, required-market and unknown-domain failures are not safe for automatic tiebreaking.
    if TruthDomain.FIXTURE_IDENTITY in domains or TruthDomain.MARKET_IDENTITY in domains or not domains:
        return DisagreementResolution(
            DisagreementStatus.QUARANTINE,
            tuple(dict.fromkeys(base.reasons + ("NON_TIEBREAKABLE_DISAGREEMENT",))),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint if third is not None else None,
            None,
            tuple(reconciliations),
            True,
            None,
        )

    if third is None:
        return DisagreementResolution(
            DisagreementStatus.QUARANTINE,
            tuple(dict.fromkeys(base.reasons + ("THIRD_SOURCE_REQUIRED",))),
            primary.fingerprint,
            fallback.fingerprint,
            None,
            None,
            tuple(reconciliations),
            True,
            None,
        )

    if third.provider_id in {primary.provider_id, fallback.provider_id}:
        return DisagreementResolution(
            DisagreementStatus.QUARANTINE,
            tuple(dict.fromkeys(base.reasons + ("THIRD_SOURCE_NOT_DISTINCT",))),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint,
            None,
            tuple(reconciliations),
            True,
            None,
        )

    if disagreement_policy.require_independent_third_source:
        groups = _independence_map(independence)
        missing = [pid for pid in (primary.provider_id, fallback.provider_id, third.provider_id) if pid not in groups]
        if missing:
            return DisagreementResolution(
                DisagreementStatus.QUARANTINE,
                tuple(dict.fromkeys(base.reasons + tuple(f"MISSING_INDEPENDENCE_EVIDENCE:{pid}" for pid in missing))),
                primary.fingerprint,
                fallback.fingerprint,
                third.fingerprint,
                None,
                tuple(reconciliations),
                True,
                None,
            )
        if len({groups[primary.provider_id], groups[fallback.provider_id], groups[third.provider_id]}) != 3:
            return DisagreementResolution(
                DisagreementStatus.QUARANTINE,
                tuple(dict.fromkeys(base.reasons + ("THIRD_SOURCE_NOT_INDEPENDENT",))),
                primary.fingerprint,
                fallback.fingerprint,
                third.fingerprint,
                None,
                tuple(reconciliations),
                True,
                None,
            )

    p3 = reconcile_snapshots(primary, third, reconciliation_policy, now=now)
    f3 = reconcile_snapshots(fallback, third, reconciliation_policy, now=now)
    reconciliations.extend((p3.fingerprint, f3.fingerprint))

    p3_acceptable = p3.status in {ReconciliationStatus.PASS, ReconciliationStatus.WATCH}
    f3_acceptable = f3.status in {ReconciliationStatus.PASS, ReconciliationStatus.WATCH}

    if p3_acceptable and not f3_acceptable:
        return DisagreementResolution(
            DisagreementStatus.WATCH,
            tuple(dict.fromkeys(base.reasons + ("RESOLVED_BY_INDEPENDENT_THIRD_SOURCE", "THIRD_SOURCE_SUPPORTS_PRIMARY"))),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint,
            primary.fingerprint,
            tuple(reconciliations),
            False,
            "INDEPENDENT_THIRD_SOURCE",
        )
    if f3_acceptable and not p3_acceptable:
        return DisagreementResolution(
            DisagreementStatus.WATCH,
            tuple(dict.fromkeys(base.reasons + ("RESOLVED_BY_INDEPENDENT_THIRD_SOURCE", "THIRD_SOURCE_SUPPORTS_FALLBACK"))),
            primary.fingerprint,
            fallback.fingerprint,
            third.fingerprint,
            fallback.fingerprint,
            tuple(reconciliations),
            False,
            "INDEPENDENT_THIRD_SOURCE",
        )

    return DisagreementResolution(
        DisagreementStatus.QUARANTINE,
        tuple(dict.fromkeys(base.reasons + ("THIRD_SOURCE_DID_NOT_RESOLVE_DISAGREEMENT",))),
        primary.fingerprint,
        fallback.fingerprint,
        third.fingerprint,
        None,
        tuple(reconciliations),
        True,
        None,
    )


def build_quarantine_record(
    resolution: DisagreementResolution,
    *,
    quarantine_id: str,
    canonical_fixture_id: str,
    now: datetime,
    policy: DisagreementPolicy,
) -> ProviderQuarantineRecord:
    _aware(now, "now")
    if resolution.status is not DisagreementStatus.QUARANTINE or not resolution.quarantine_required:
        raise ValueError("only quarantine-required resolutions may create quarantine records")
    fingerprints = [resolution.primary_fingerprint, resolution.fallback_fingerprint]
    if resolution.third_fingerprint is not None:
        fingerprints.append(resolution.third_fingerprint)
    return ProviderQuarantineRecord(
        quarantine_id=quarantine_id,
        canonical_fixture_id=canonical_fixture_id,
        created_at=now,
        expires_at=now + timedelta(seconds=policy.quarantine_ttl_seconds),
        reason_codes=resolution.reasons,
        source_snapshot_fingerprints=tuple(fingerprints),
    )
