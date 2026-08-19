from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from app.release.canonical import canonical_sha256
from .attestation import SignedAttestation, TrustStore
from .identity_access import AuthenticatedSession, SessionPolicy, validate_session

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class AuthenticatedAuditEvent:
    event_id: str
    actor_principal_id: str
    actor_session_fingerprint: str
    action: str
    resource: str
    occurred_at: datetime
    outcome: str
    details_sha256: str
    previous_event_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.actor_principal_id.strip() or not self.action.strip() or not self.resource.strip():
            raise ValueError("event id, actor, action and resource are required")
        if self.outcome not in {"ALLOW", "DENY", "ERROR"}:
            raise ValueError("outcome must be ALLOW, DENY or ERROR")
        _aware(self.occurred_at, "occurred_at")
        if not _HEX64.fullmatch(self.actor_session_fingerprint):
            raise ValueError("actor_session_fingerprint must be SHA-256")
        if not _HEX64.fullmatch(self.details_sha256):
            raise ValueError("details_sha256 must be SHA-256")
        if self.previous_event_sha256 is not None and not _HEX64.fullmatch(self.previous_event_sha256):
            raise ValueError("previous_event_sha256 must be SHA-256")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class SignedAuditEvidence:
    event: AuthenticatedAuditEvent
    attestation: SignedAttestation

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class AuditAuthenticationResult:
    passed: bool
    reasons: tuple[str, ...]


def verify_audit_evidence(
    evidence: SignedAuditEvidence,
    *,
    trust_store: TrustStore,
    actor_session: AuthenticatedSession,
    now: datetime,
    session_policy: SessionPolicy,
    require_production_trust: bool = False,
    max_event_age_hours: int = 24,
) -> AuditAuthenticationResult:
    _aware(now, "now")
    reasons: list[str] = []
    event = evidence.event
    if event.actor_principal_id != actor_session.principal.principal_id:
        reasons.append("AUDIT_ACTOR_IDENTITY_MISMATCH")
    if event.actor_session_fingerprint != actor_session.fingerprint:
        reasons.append("AUDIT_SESSION_FINGERPRINT_MISMATCH")
    session_result = validate_session(actor_session, now=now, policy=session_policy)
    if not session_result.passed:
        reasons.extend(f"AUDIT_ACTOR_SESSION:{reason}" for reason in session_result.reasons)
    if event.occurred_at > now + timedelta(minutes=5):
        reasons.append("AUDIT_EVENT_FROM_FUTURE")
    if now - event.occurred_at > timedelta(hours=max_event_age_hours):
        reasons.append("AUDIT_EVENT_TOO_OLD")

    verification = trust_store.verify(
        evidence.attestation,
        now=now,
        required_purpose="audit_authentication",
        expected_subject_sha256=event.fingerprint,
        expected_predicate_sha256=event.details_sha256,
        require_production_trust=require_production_trust,
    )
    if not verification.passed:
        reasons.extend(f"AUDIT_ATTESTATION:{reason}" for reason in verification.reasons)
    return AuditAuthenticationResult(not reasons, tuple(dict.fromkeys(reasons)))


def verify_audit_chain(events: tuple[AuthenticatedAuditEvent, ...]) -> AuditAuthenticationResult:
    reasons: list[str] = []
    seen_ids: set[str] = set()
    previous: str | None = None
    for index, event in enumerate(events):
        if event.event_id in seen_ids:
            reasons.append(f"DUPLICATE_AUDIT_EVENT_ID:{event.event_id}")
        seen_ids.add(event.event_id)
        if index == 0:
            if event.previous_event_sha256 is not None:
                reasons.append("AUDIT_CHAIN_FIRST_EVENT_HAS_PREVIOUS_HASH")
        elif event.previous_event_sha256 != previous:
            reasons.append(f"AUDIT_CHAIN_BROKEN:{event.event_id}")
        previous = event.fingerprint
    return AuditAuthenticationResult(not reasons, tuple(dict.fromkeys(reasons)))
