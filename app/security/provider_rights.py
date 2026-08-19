from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_sha256(value: str, name: str) -> None:
    text = value.strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256")


def _clean_unique(values: tuple[str, ...], name: str, *, required: bool = False) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if required and not cleaned:
        raise ValueError(f"{name} is required")
    if any(not value for value in cleaned):
        raise ValueError(f"{name} may not contain blank values")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{name} may not contain duplicates")
    return cleaned


class ProviderRightsReviewOutcome(str, Enum):
    APPROVED_FOR_GOVERNED_USE = "APPROVED_FOR_GOVERNED_USE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class RightsEvidenceStrength(str, Enum):
    PUBLIC_TERMS_REVIEWED = "PUBLIC_TERMS_REVIEWED"
    CONTRACTUAL = "CONTRACTUAL"
    UNKNOWN = "UNKNOWN"


class DataForm(str, Enum):
    RAW = "RAW"
    DERIVED = "DERIVED"
    AGGREGATED = "AGGREGATED"
    MODEL_ARTIFACT = "MODEL_ARTIFACT"


class ProviderUseAction(str, Enum):
    INGEST = "INGEST"
    CACHE = "CACHE"
    STORE_RAW = "STORE_RAW"
    RETAIN_HISTORY = "RETAIN_HISTORY"
    CREATE_DERIVED = "CREATE_DERIVED"
    TRAIN_MODEL = "TRAIN_MODEL"
    INTERNAL_ANALYTICS = "INTERNAL_ANALYTICS"
    DISPLAY_INTERNAL = "DISPLAY_INTERNAL"
    DISPLAY_CUSTOMER = "DISPLAY_CUSTOMER"
    REDISTRIBUTE_PUBLIC = "REDISTRIBUTE_PUBLIC"
    REDISTRIBUTE_CUSTOMER = "REDISTRIBUTE_CUSTOMER"
    COMMERCIAL_USE = "COMMERCIAL_USE"
    BACKUP = "BACKUP"
    EXPORT = "EXPORT"
    SUBLICENSE = "SUBLICENSE"


class TerminationTreatment(str, Enum):
    DELETE_ALL_PROVIDER_DATA = "DELETE_ALL_PROVIDER_DATA"
    DELETE_RAW_RETAIN_DERIVED = "DELETE_RAW_RETAIN_DERIVED"
    RETAIN_GOVERNED_DATA = "RETAIN_GOVERNED_DATA"
    EXTERNAL_REVIEW_REQUIRED = "EXTERNAL_REVIEW_REQUIRED"


@dataclass(frozen=True)
class ProviderRightsProfile:
    provider_id: str
    profile_version: str
    sports: tuple[str, ...]
    competition_scopes: tuple[str, ...]
    territories: tuple[str, ...]
    purpose_ids: tuple[str, ...]
    allow_ingest: bool
    allow_cache: bool
    allow_raw_storage: bool
    allow_historical_retention: bool
    allow_derived_data: bool
    allow_model_training: bool
    allow_internal_analytics: bool
    allow_internal_display: bool
    allow_customer_display: bool
    allow_public_redistribution: bool
    allow_customer_redistribution: bool
    allow_commercial_use: bool
    allow_backup: bool
    allow_export: bool
    allow_sublicense: bool
    max_raw_retention_days: int | None
    max_cache_retention_minutes: int | None
    attribution_required: bool
    attribution_reference: str | None
    termination_treatment: TerminationTreatment

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.profile_version.strip():
            raise ValueError("provider_id and profile_version are required")
        _clean_unique(self.sports, "sports", required=True)
        _clean_unique(self.competition_scopes, "competition_scopes", required=False)
        _clean_unique(self.territories, "territories", required=True)
        _clean_unique(self.purpose_ids, "purpose_ids", required=True)
        if self.max_raw_retention_days is not None:
            if isinstance(self.max_raw_retention_days, bool) or not isinstance(self.max_raw_retention_days, int):
                raise TypeError("max_raw_retention_days must be int or None")
            if self.max_raw_retention_days < 0:
                raise ValueError("max_raw_retention_days may not be negative")
        if self.max_cache_retention_minutes is not None:
            if isinstance(self.max_cache_retention_minutes, bool) or not isinstance(self.max_cache_retention_minutes, int):
                raise TypeError("max_cache_retention_minutes must be int or None")
            if self.max_cache_retention_minutes < 0:
                raise ValueError("max_cache_retention_minutes may not be negative")
        if self.allow_historical_retention and not self.allow_raw_storage:
            raise ValueError("historical retention requires raw storage rights")
        if self.allow_model_training and not self.allow_derived_data:
            raise ValueError("model training requires derived-data rights")
        if self.allow_customer_display and not self.allow_internal_display:
            raise ValueError("customer display requires internal display rights")
        if self.allow_customer_redistribution and not self.allow_customer_display:
            raise ValueError("customer redistribution requires customer display rights")
        if self.allow_public_redistribution and not self.allow_customer_display:
            raise ValueError("public redistribution requires customer display rights")
        if self.allow_sublicense and not self.allow_customer_redistribution:
            raise ValueError("sublicensing requires customer redistribution rights")
        if self.attribution_required and not (self.attribution_reference or "").strip():
            raise ValueError("attribution_reference is required when attribution is required")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderRightsEvidence:
    evidence_id: str
    provider_id: str
    profile_fingerprint: str
    source_reference: str
    terms_sha256: str
    reviewer_role: str
    reviewed_at: datetime
    valid_from: datetime
    valid_until: datetime
    outcome: ProviderRightsReviewOutcome
    evidence_strength: RightsEvidenceStrength
    revoked: bool = False
    independent_review_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.provider_id.strip() or not self.source_reference.strip() or not self.reviewer_role.strip():
            raise ValueError("evidence_id, provider_id, source_reference and reviewer_role are required")
        _require_sha256(self.profile_fingerprint, "profile_fingerprint")
        _require_sha256(self.terms_sha256, "terms_sha256")
        _require_aware(self.reviewed_at, "reviewed_at")
        _require_aware(self.valid_from, "valid_from")
        _require_aware(self.valid_until, "valid_until")
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.reviewed_at > self.valid_until:
            raise ValueError("reviewed_at may not be after valid_until")
        if self.evidence_strength is RightsEvidenceStrength.CONTRACTUAL and not (self.independent_review_reference or "").strip():
            raise ValueError("contractual evidence requires independent_review_reference")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderUseRequest:
    request_id: str
    provider_id: str
    purpose_id: str
    sport: str
    competition_scope: str | None
    territory: str
    action: ProviderUseAction
    data_form: DataForm
    requested_raw_retention_days: int | None
    requested_cache_retention_minutes: int | None
    attribution_planned: bool
    requested_at: datetime
    commercial_context: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.provider_id.strip() or not self.purpose_id.strip() or not self.sport.strip() or not self.territory.strip():
            raise ValueError("request_id, provider_id, purpose_id, sport and territory are required")
        _require_aware(self.requested_at, "requested_at")
        if self.competition_scope is not None and not self.competition_scope.strip():
            raise ValueError("competition_scope may not be blank")
        for value, name in (
            (self.requested_raw_retention_days, "requested_raw_retention_days"),
            (self.requested_cache_retention_minutes, "requested_cache_retention_minutes"),
        ):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{name} must be int or None")
                if value < 0:
                    raise ValueError(f"{name} may not be negative")


class ProviderRightsStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderRightsAssessment:
    status: ProviderRightsStatus
    reasons: tuple[str, ...]
    profile_fingerprint: str
    evidence_fingerprint: str | None
    legal_rights_certified: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.profile_fingerprint, "profile_fingerprint")
        if self.evidence_fingerprint is not None:
            _require_sha256(self.evidence_fingerprint, "evidence_fingerprint")
        if self.legal_rights_certified:
            raise ValueError("software may not self-certify provider legal rights")


def _action_allowed(profile: ProviderRightsProfile, action: ProviderUseAction) -> bool:
    mapping = {
        ProviderUseAction.INGEST: profile.allow_ingest,
        ProviderUseAction.CACHE: profile.allow_cache,
        ProviderUseAction.STORE_RAW: profile.allow_raw_storage,
        ProviderUseAction.RETAIN_HISTORY: profile.allow_historical_retention,
        ProviderUseAction.CREATE_DERIVED: profile.allow_derived_data,
        ProviderUseAction.TRAIN_MODEL: profile.allow_model_training,
        ProviderUseAction.INTERNAL_ANALYTICS: profile.allow_internal_analytics,
        ProviderUseAction.DISPLAY_INTERNAL: profile.allow_internal_display,
        ProviderUseAction.DISPLAY_CUSTOMER: profile.allow_customer_display,
        ProviderUseAction.REDISTRIBUTE_PUBLIC: profile.allow_public_redistribution,
        ProviderUseAction.REDISTRIBUTE_CUSTOMER: profile.allow_customer_redistribution,
        ProviderUseAction.COMMERCIAL_USE: profile.allow_commercial_use,
        ProviderUseAction.BACKUP: profile.allow_backup,
        ProviderUseAction.EXPORT: profile.allow_export,
        ProviderUseAction.SUBLICENSE: profile.allow_sublicense,
    }
    return mapping[action]


def _high_risk_action(action: ProviderUseAction, commercial_context: bool) -> bool:
    return commercial_context or action in {
        ProviderUseAction.DISPLAY_CUSTOMER,
        ProviderUseAction.REDISTRIBUTE_PUBLIC,
        ProviderUseAction.REDISTRIBUTE_CUSTOMER,
        ProviderUseAction.COMMERCIAL_USE,
        ProviderUseAction.SUBLICENSE,
    }


def evaluate_provider_rights(
    profile: ProviderRightsProfile,
    evidence: ProviderRightsEvidence | None,
    request: ProviderUseRequest,
    *,
    now: datetime,
    contract_warning_days: int = 30,
) -> ProviderRightsAssessment:
    _require_aware(now, "now")
    if isinstance(contract_warning_days, bool) or not isinstance(contract_warning_days, int):
        raise TypeError("contract_warning_days must be int")
    if contract_warning_days < 0:
        raise ValueError("contract_warning_days may not be negative")

    blockers: list[str] = []
    watches: list[str] = []

    if request.requested_at > now:
        blockers.append("FUTURE_USE_REQUEST")
    if request.provider_id != profile.provider_id:
        blockers.append("PROVIDER_PROFILE_MISMATCH")
    if request.purpose_id not in profile.purpose_ids:
        blockers.append("PURPOSE_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS")
    if request.sport not in profile.sports:
        blockers.append("SPORT_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS")
    if profile.competition_scopes and request.competition_scope not in profile.competition_scopes:
        blockers.append("COMPETITION_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS")
    if request.territory not in profile.territories:
        blockers.append("TERRITORY_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS")
    if not _action_allowed(profile, request.action):
        blockers.append(f"ACTION_NOT_AUTHORIZED:{request.action.value}")

    if request.commercial_context and not profile.allow_commercial_use:
        blockers.append("COMMERCIAL_CONTEXT_NOT_AUTHORIZED")

    if request.requested_raw_retention_days is not None:
        if not profile.allow_raw_storage:
            blockers.append("RAW_RETENTION_REQUESTED_WITHOUT_STORAGE_RIGHT")
        if profile.max_raw_retention_days is not None and request.requested_raw_retention_days > profile.max_raw_retention_days:
            blockers.append("RAW_RETENTION_EXCEEDS_PROVIDER_LIMIT")
    if request.requested_cache_retention_minutes is not None:
        if not profile.allow_cache:
            blockers.append("CACHE_RETENTION_REQUESTED_WITHOUT_CACHE_RIGHT")
        if profile.max_cache_retention_minutes is not None and request.requested_cache_retention_minutes > profile.max_cache_retention_minutes:
            blockers.append("CACHE_RETENTION_EXCEEDS_PROVIDER_LIMIT")

    if profile.attribution_required and not request.attribution_planned:
        blockers.append("REQUIRED_ATTRIBUTION_NOT_PLANNED")

    if request.data_form is DataForm.RAW and request.action in {
        ProviderUseAction.CREATE_DERIVED,
        ProviderUseAction.TRAIN_MODEL,
    }:
        # Raw input may be used to create derivatives only when the explicit derivative/model rights exist.
        if request.action is ProviderUseAction.CREATE_DERIVED and not profile.allow_derived_data:
            blockers.append("DERIVATIVE_RIGHT_REQUIRED")
        if request.action is ProviderUseAction.TRAIN_MODEL and not profile.allow_model_training:
            blockers.append("MODEL_TRAINING_RIGHT_REQUIRED")

    if evidence is None:
        blockers.append("MISSING_PROVIDER_RIGHTS_EVIDENCE")
    else:
        if evidence.provider_id != profile.provider_id:
            blockers.append("RIGHTS_EVIDENCE_PROVIDER_MISMATCH")
        if evidence.profile_fingerprint != profile.fingerprint:
            blockers.append("RIGHTS_EVIDENCE_PROFILE_MISMATCH")
        if evidence.reviewed_at > now or evidence.valid_from > now:
            blockers.append("FUTURE_OR_NOT_YET_VALID_RIGHTS_EVIDENCE")
        if evidence.valid_until <= now:
            blockers.append("EXPIRED_PROVIDER_RIGHTS_EVIDENCE")
        elif (evidence.valid_until - now).days < contract_warning_days:
            watches.append("PROVIDER_RIGHTS_EXPIRING_SOON")
        if evidence.revoked:
            blockers.append("REVOKED_PROVIDER_RIGHTS_EVIDENCE")
        if evidence.outcome is ProviderRightsReviewOutcome.REJECTED:
            blockers.append("PROVIDER_RIGHTS_REJECTED")
        elif evidence.outcome is ProviderRightsReviewOutcome.REVIEW_REQUIRED:
            watches.append("PROVIDER_RIGHTS_REVIEW_REQUIRED")
        if evidence.evidence_strength is RightsEvidenceStrength.UNKNOWN:
            blockers.append("UNKNOWN_RIGHTS_EVIDENCE_STRENGTH")
        if _high_risk_action(request.action, request.commercial_context):
            if evidence.evidence_strength is not RightsEvidenceStrength.CONTRACTUAL:
                watches.append("HIGH_RISK_USE_REQUIRES_CONTRACTUAL_EVIDENCE_REVIEW")
            if not (evidence.independent_review_reference or "").strip():
                blockers.append("HIGH_RISK_USE_REQUIRES_INDEPENDENT_REVIEW")

    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return ProviderRightsAssessment(
            ProviderRightsStatus.BLOCK,
            reasons,
            profile.fingerprint,
            evidence.fingerprint if evidence else None,
        )
    if watches:
        return ProviderRightsAssessment(
            ProviderRightsStatus.WATCH,
            reasons,
            profile.fingerprint,
            evidence.fingerprint if evidence else None,
        )
    return ProviderRightsAssessment(
        ProviderRightsStatus.PASS,
        (),
        profile.fingerprint,
        evidence.fingerprint if evidence else None,
    )


@dataclass(frozen=True)
class ProviderRightsBinding:
    provider_id: str
    source_asset_id: str
    profile_fingerprint: str
    evidence_fingerprint: str
    bound_at: datetime

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.source_asset_id.strip():
            raise ValueError("provider_id and source_asset_id are required")
        _require_sha256(self.profile_fingerprint, "profile_fingerprint")
        _require_sha256(self.evidence_fingerprint, "evidence_fingerprint")
        _require_aware(self.bound_at, "bound_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class DerivedDataRightsLineage:
    derived_asset_id: str
    source_bindings: tuple[ProviderRightsBinding, ...]
    transformation_reference: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.derived_asset_id.strip() or not self.transformation_reference.strip():
            raise ValueError("derived_asset_id and transformation_reference are required")
        _require_aware(self.created_at, "created_at")
        if not self.source_bindings:
            raise ValueError("derived data requires at least one provider rights binding")
        provider_asset_pairs = [(b.provider_id, b.source_asset_id) for b in self.source_bindings]
        if len(set(provider_asset_pairs)) != len(provider_asset_pairs):
            raise ValueError("duplicate provider/source binding in derived lineage")
        if any(binding.bound_at > self.created_at for binding in self.source_bindings):
            raise ValueError("rights binding may not be newer than derived asset")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def aggregate_provider_rights(assessments: Iterable[ProviderRightsAssessment]) -> ProviderRightsAssessment:
    items = tuple(assessments)
    if not items:
        raise ValueError("at least one provider rights assessment is required")
    blockers: list[str] = []
    watches: list[str] = []
    for index, item in enumerate(items):
        if item.status is ProviderRightsStatus.BLOCK:
            blockers.extend(f"SOURCE_{index}:{reason}" for reason in (item.reasons or ("PROVIDER_RIGHTS_BLOCKED",)))
        elif item.status is ProviderRightsStatus.WATCH:
            watches.extend(f"SOURCE_{index}:{reason}" for reason in (item.reasons or ("PROVIDER_RIGHTS_WATCH",)))
    aggregate_fp = canonical_sha256(tuple((item.profile_fingerprint, item.evidence_fingerprint, item.status.value) for item in items))
    if blockers:
        return ProviderRightsAssessment(ProviderRightsStatus.BLOCK, tuple(blockers + watches), aggregate_fp, None)
    if watches:
        return ProviderRightsAssessment(ProviderRightsStatus.WATCH, tuple(watches), aggregate_fp, None)
    return ProviderRightsAssessment(ProviderRightsStatus.PASS, (), aggregate_fp, None)
