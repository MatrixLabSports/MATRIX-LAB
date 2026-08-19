from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .provider_rights import ProviderRightsEvidence, ProviderRightsProfile


class TermsTransitionStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TermsTransitionResult:
    status: TermsTransitionStatus
    reasons: tuple[str, ...]


def evaluate_terms_transition(
    previous_profile: ProviderRightsProfile,
    previous_evidence: ProviderRightsEvidence,
    current_profile: ProviderRightsProfile,
    current_evidence: ProviderRightsEvidence,
) -> TermsTransitionResult:
    blockers: list[str] = []
    watches: list[str] = []

    if previous_profile.provider_id != current_profile.provider_id:
        blockers.append("PROVIDER_CHANGED_ACROSS_TERMS_TRANSITION")
    if previous_evidence.provider_id != previous_profile.provider_id:
        blockers.append("PREVIOUS_EVIDENCE_PROVIDER_MISMATCH")
    if current_evidence.provider_id != current_profile.provider_id:
        blockers.append("CURRENT_EVIDENCE_PROVIDER_MISMATCH")
    if previous_evidence.profile_fingerprint != previous_profile.fingerprint:
        blockers.append("PREVIOUS_EVIDENCE_PROFILE_MISMATCH")
    if current_evidence.profile_fingerprint != current_profile.fingerprint:
        blockers.append("CURRENT_EVIDENCE_PROFILE_MISMATCH")
    if current_evidence.reviewed_at < previous_evidence.reviewed_at:
        blockers.append("RIGHTS_REVIEW_TIME_REGRESSION")
    if current_evidence.evidence_id == previous_evidence.evidence_id and current_evidence.fingerprint != previous_evidence.fingerprint:
        blockers.append("RIGHTS_EVIDENCE_ID_REUSED_FOR_CHANGED_CONTENT")

    terms_changed = current_evidence.terms_sha256 != previous_evidence.terms_sha256
    profile_changed = current_profile.fingerprint != previous_profile.fingerprint
    version_changed = current_profile.profile_version != previous_profile.profile_version

    if terms_changed and not version_changed:
        blockers.append("TERMS_CHANGED_WITHOUT_PROFILE_VERSION_BUMP")
    if profile_changed and not version_changed:
        blockers.append("RIGHTS_PROFILE_CHANGED_WITHOUT_VERSION_BUMP")
    if version_changed and not terms_changed and not profile_changed:
        watches.append("VERSION_BUMP_WITHOUT_TERMS_OR_PROFILE_CHANGE")
    if terms_changed and current_evidence.source_reference == previous_evidence.source_reference:
        watches.append("TERMS_HASH_CHANGED_WITH_SAME_SOURCE_REFERENCE")

    if blockers:
        return TermsTransitionResult(TermsTransitionStatus.BLOCK, tuple(dict.fromkeys(blockers + watches)))
    if watches:
        return TermsTransitionResult(TermsTransitionStatus.WATCH, tuple(dict.fromkeys(watches)))
    return TermsTransitionResult(TermsTransitionStatus.PASS, ())
