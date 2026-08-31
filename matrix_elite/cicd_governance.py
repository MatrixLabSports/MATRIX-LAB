from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


REQUIRED_GATES = (
    "lint", "unit", "integration", "data", "security", "secret_scan",
    "dependency_scan", "coverage", "schema", "sport_boundary",
    "model_validation", "build", "sbom", "artifact_signing",
)


def _sha(value: str, name: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{name}_REQUIRED")
    int(value, 16)


@dataclass(frozen=True)
class CIRunEvidence:
    commit_sha: str
    branch: str
    completed_at: datetime
    gates: Mapping[str, bool]
    dependency_lock_sha256: str
    sbom_sha256: str
    build_artifact_sha256: str
    artifact_signature_evidence_sha256: str
    dependency_lock_verified: bool
    sbom_verified: bool
    artifact_signature_verified: bool
    main_protected: bool
    human_release_approved: bool
    automatic_model_promotion: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if len(self.commit_sha) != 40:
            raise ValueError("CI_COMMIT_SHA_REQUIRED")
        int(self.commit_sha, 16)
        if not self.branch.strip():
            raise ValueError("CI_BRANCH_REQUIRED")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("CI_COMPLETED_AT_MUST_BE_AWARE")
        for name in ("dependency_lock_sha256", "sbom_sha256", "build_artifact_sha256", "artifact_signature_evidence_sha256"):
            _sha(getattr(self, name), name.upper())


def ci_acceptance_gate(evidence: CIRunEvidence, *, expected_commit_sha: str, production_release: bool) -> dict[str, object]:
    reasons: list[str] = []
    if evidence.commit_sha != expected_commit_sha:
        reasons.append("CI_COMMIT_MISMATCH")
    missing = [gate for gate in REQUIRED_GATES if gate not in evidence.gates]
    failed = [gate for gate in REQUIRED_GATES if evidence.gates.get(gate) is False]
    if missing:
        reasons.append("CI_GATES_MISSING:" + ",".join(sorted(missing)))
    if failed:
        reasons.append("CI_GATES_FAILED:" + ",".join(sorted(failed)))
    if not evidence.dependency_lock_verified:
        reasons.append("DEPENDENCY_LOCK_VERIFICATION_REQUIRED")
    if not evidence.sbom_verified:
        reasons.append("SBOM_VERIFICATION_REQUIRED")
    if not evidence.artifact_signature_verified:
        reasons.append("ARTIFACT_SIGNATURE_VERIFICATION_REQUIRED")
    if not evidence.main_protected:
        reasons.append("MAIN_BRANCH_PROTECTION_REQUIRED")
    if evidence.automatic_model_promotion:
        reasons.append("AUTOMATIC_MODEL_PROMOTION_FORBIDDEN")
    if evidence.automatic_provider_switch:
        reasons.append("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
    if evidence.automatic_wagering:
        reasons.append("AUTOMATIC_WAGERING_FORBIDDEN")
    if production_release and not evidence.human_release_approved:
        reasons.append("HUMAN_RELEASE_APPROVAL_REQUIRED")
    return {"pass": not reasons, "reasons": tuple(reasons)}
