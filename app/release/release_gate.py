from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.security.security_gate import SecurityGateResult, SecurityStatus

from .canonical import file_sha256
from .evidence import CIEvidenceSet, TestRunEvidence
from .provenance import ReleaseProvenance


class ReleaseGateStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ReleaseGateInput:
    provenance: ReleaseProvenance
    artifact_path: Path
    ci_evidence: CIEvidenceSet
    tests: TestRunEvidence
    security_result: SecurityGateResult
    release_notes_present: bool
    rollback_plan_present: bool
    evidence_bundle_verified: bool


@dataclass(frozen=True)
class ReleaseGateResult:
    status: ReleaseGateStatus
    reasons: tuple[str, ...]
    integration_review_eligible: bool
    production_release_enabled: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.production_release_enabled:
            raise ValueError("V13 release gate may not authorize production release")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("release gate may never enable model promotion or wagering")
        if self.integration_review_eligible and self.status is not ReleaseGateStatus.PASS:
            raise ValueError("only PASS can be eligible for integration review")


def evaluate_release_gate(
    data: ReleaseGateInput,
    *,
    now: datetime,
    max_ci_age_hours: int = 24,
) -> ReleaseGateResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    blockers: list[str] = []
    watches: list[str] = []

    if not data.provenance.source_tree_clean:
        blockers.append("SOURCE_TREE_NOT_CLEAN")
    if not data.provenance.source_commit_verified:
        blockers.append("SOURCE_COMMIT_NOT_VERIFIED")
    if not data.provenance.builder_identity_verified:
        blockers.append("BUILDER_IDENTITY_NOT_VERIFIED")
    if data.provenance.commit_sha != data.ci_evidence.commit_sha:
        blockers.append("PROVENANCE_CI_COMMIT_MISMATCH")
    if data.provenance.ci_evidence_sha256 != data.ci_evidence.fingerprint:
        blockers.append("CI_EVIDENCE_FINGERPRINT_MISMATCH")

    artifact = Path(data.artifact_path)
    if not artifact.exists() or not artifact.is_file() or artifact.is_symlink():
        blockers.append("RELEASE_ARTIFACT_MISSING_OR_UNSAFE")
    elif file_sha256(artifact) != data.provenance.artifact_sha256:
        blockers.append("RELEASE_ARTIFACT_HASH_MISMATCH")

    missing = data.ci_evidence.missing_required_stages()
    if missing:
        blockers.extend(f"MISSING_CI_STAGE:{stage}" for stage in missing)
    failed = data.ci_evidence.failed_stages()
    if failed:
        blockers.extend(f"FAILED_CI_STAGE:{stage}" for stage in failed)
    stale = data.ci_evidence.stale_stages(now=now, max_age_hours=max_ci_age_hours)
    if stale:
        blockers.extend(f"STALE_OR_FUTURE_CI_STAGE:{stage}" for stage in stale)

    if not data.tests.clean:
        blockers.append("TEST_RUN_NOT_CLEAN")

    if data.security_result.status is SecurityStatus.BLOCK:
        blockers.append("SECURITY_GATE_BLOCKED")
    elif data.security_result.status is SecurityStatus.WATCH:
        watches.append("SECURITY_GATE_REQUIRES_REVIEW")

    if not data.release_notes_present:
        blockers.append("RELEASE_NOTES_MISSING")
    if not data.rollback_plan_present:
        blockers.append("ROLLBACK_PLAN_MISSING")
    if not data.evidence_bundle_verified:
        blockers.append("EVIDENCE_BUNDLE_NOT_VERIFIED")

    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return ReleaseGateResult(ReleaseGateStatus.BLOCK, reasons, False)
    if watches:
        return ReleaseGateResult(ReleaseGateStatus.WATCH, reasons, False)
    return ReleaseGateResult(ReleaseGateStatus.PASS, (), True)
