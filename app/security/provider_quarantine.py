from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.release.canonical import canonical_sha256


def _required(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


class QuarantineState(str, Enum):
    OPEN = "OPEN"
    RELEASED = "RELEASED"


class QuarantineReleaseStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderQuarantineRecord:
    quarantine_id: str
    canonical_fixture_id: str
    created_at: datetime
    expires_at: datetime
    reason_codes: tuple[str, ...]
    source_snapshot_fingerprints: tuple[str, ...]
    state: QuarantineState = QuarantineState.OPEN
    automatic_release: bool = False

    def __post_init__(self) -> None:
        _required(self.quarantine_id, "quarantine_id")
        _required(self.canonical_fixture_id, "canonical_fixture_id")
        _aware(self.created_at, "created_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if not self.reason_codes:
            raise ValueError("reason_codes are required")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes may not contain duplicates")
        if len(self.source_snapshot_fingerprints) < 2:
            raise ValueError("at least two source snapshot fingerprints are required")
        if len(set(self.source_snapshot_fingerprints)) != len(self.source_snapshot_fingerprints):
            raise ValueError("source snapshot fingerprints may not contain duplicates")
        for index, fingerprint in enumerate(self.source_snapshot_fingerprints):
            _sha256(fingerprint, f"source_snapshot_fingerprints[{index}]")
        if self.automatic_release:
            raise ValueError("provider quarantine may never auto-release")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class QuarantineReleaseEvidence:
    quarantine_fingerprint: str
    resolution_fingerprint: str
    reviewed_at: datetime
    reviewer_id: str
    independent_reviewer: bool
    human_approved: bool
    required_checks_passed: bool

    def __post_init__(self) -> None:
        _sha256(self.quarantine_fingerprint, "quarantine_fingerprint")
        _sha256(self.resolution_fingerprint, "resolution_fingerprint")
        _aware(self.reviewed_at, "reviewed_at")
        _required(self.reviewer_id, "reviewer_id")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class QuarantineReleaseAssessment:
    status: QuarantineReleaseStatus
    reasons: tuple[str, ...]
    quarantine_fingerprint: str
    release_evidence_fingerprint: str | None
    automatic_release: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_release:
            raise ValueError("release must remain explicit")
        if self.automatic_provider_switch:
            raise ValueError("release assessment may not switch providers")
        if self.automatic_wagering:
            raise ValueError("release assessment may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_quarantine_release(
    record: ProviderQuarantineRecord,
    evidence: QuarantineReleaseEvidence | None,
    *,
    now: datetime,
) -> QuarantineReleaseAssessment:
    _aware(now, "now")
    reasons: list[str] = []
    watch: list[str] = []

    if record.state is not QuarantineState.OPEN:
        reasons.append("QUARANTINE_NOT_OPEN")
    if now >= record.expires_at:
        reasons.append("QUARANTINE_EXPIRED_REQUIRES_NEW_REVIEW")
    if evidence is None:
        reasons.append("MISSING_RELEASE_EVIDENCE")
        return QuarantineReleaseAssessment(
            QuarantineReleaseStatus.BLOCK,
            tuple(reasons),
            record.fingerprint,
            None,
        )

    if evidence.quarantine_fingerprint != record.fingerprint:
        reasons.append("QUARANTINE_FINGERPRINT_MISMATCH")
    if evidence.reviewed_at < record.created_at:
        reasons.append("REVIEW_PREDATES_QUARANTINE")
    if evidence.reviewed_at > now:
        reasons.append("REVIEW_FROM_FUTURE")
    if not evidence.human_approved:
        reasons.append("RELEASE_NOT_HUMAN_APPROVED")
    if not evidence.independent_reviewer:
        reasons.append("RELEASE_NOT_INDEPENDENTLY_REVIEWED")
    if not evidence.required_checks_passed:
        reasons.append("RELEASE_CHECKS_NOT_PASSED")

    if reasons:
        status = QuarantineReleaseStatus.BLOCK
        all_reasons = tuple(dict.fromkeys(reasons + watch))
    elif watch:
        status = QuarantineReleaseStatus.WATCH
        all_reasons = tuple(dict.fromkeys(watch))
    else:
        status = QuarantineReleaseStatus.PASS
        all_reasons = ()

    return QuarantineReleaseAssessment(
        status,
        all_reasons,
        record.fingerprint,
        evidence.fingerprint,
    )
