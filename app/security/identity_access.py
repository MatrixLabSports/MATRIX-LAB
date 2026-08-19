from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from app.release.canonical import canonical_sha256
from .rbac import Permission, Principal, is_allowed

_SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class AuthenticationStrength(str, Enum):
    PASSWORD_ONLY = "PASSWORD_ONLY"
    MFA = "MFA"
    PHISHING_RESISTANT_MFA = "PHISHING_RESISTANT_MFA"


_STRENGTH_RANK = {
    AuthenticationStrength.PASSWORD_ONLY: 1,
    AuthenticationStrength.MFA: 2,
    AuthenticationStrength.PHISHING_RESISTANT_MFA: 3,
}


@dataclass(frozen=True)
class AuthenticatedSession:
    session_id: str
    principal: Principal
    identity_provider: str
    authenticated_at: datetime
    expires_at: datetime
    auth_strength: AuthenticationStrength
    identity_verified: bool
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not _SESSION_ID.fullmatch(self.session_id):
            raise ValueError("session_id must be 8-128 safe characters")
        if not self.identity_provider.strip():
            raise ValueError("identity_provider is required")
        _aware(self.authenticated_at, "authenticated_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.authenticated_at:
            raise ValueError("expires_at must be after authenticated_at")
        if self.revoked_at is not None:
            _aware(self.revoked_at, "revoked_at")
            if self.revoked_at < self.authenticated_at:
                raise ValueError("revoked_at cannot precede authentication")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class SessionPolicy:
    max_session_age_minutes: int = 480
    max_future_skew_seconds: int = 300
    required_strength: AuthenticationStrength = AuthenticationStrength.MFA

    def __post_init__(self) -> None:
        if self.max_session_age_minutes <= 0:
            raise ValueError("max_session_age_minutes must be > 0")
        if self.max_future_skew_seconds < 0:
            raise ValueError("max_future_skew_seconds must be >= 0")


@dataclass(frozen=True)
class SessionValidationResult:
    passed: bool
    reasons: tuple[str, ...]


def validate_session(session: AuthenticatedSession, *, now: datetime, policy: SessionPolicy) -> SessionValidationResult:
    _aware(now, "now")
    reasons: list[str] = []
    if not session.identity_verified:
        reasons.append("IDENTITY_NOT_VERIFIED")
    if session.authenticated_at > now + timedelta(seconds=policy.max_future_skew_seconds):
        reasons.append("AUTHENTICATION_FROM_FUTURE")
    if now >= session.expires_at:
        reasons.append("SESSION_EXPIRED")
    if now - session.authenticated_at > timedelta(minutes=policy.max_session_age_minutes):
        reasons.append("SESSION_TOO_OLD")
    if session.revoked_at is not None and now >= session.revoked_at:
        reasons.append("SESSION_REVOKED")
    if _STRENGTH_RANK[session.auth_strength] < _STRENGTH_RANK[policy.required_strength]:
        reasons.append("AUTHENTICATION_STRENGTH_INSUFFICIENT")
    return SessionValidationResult(not reasons, tuple(dict.fromkeys(reasons)))


@dataclass(frozen=True)
class TemporaryPermissionGrant:
    grant_id: str
    principal_id: str
    permission: Permission
    granted_by: str
    granted_at: datetime
    valid_from: datetime
    valid_until: datetime
    reason: str
    ticket_id: str
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.grant_id.strip() or not self.principal_id.strip() or not self.granted_by.strip():
            raise ValueError("grant_id, principal_id and granted_by are required")
        if not self.reason.strip() or not self.ticket_id.strip():
            raise ValueError("reason and ticket_id are required")
        for name, value in (("granted_at", self.granted_at), ("valid_from", self.valid_from), ("valid_until", self.valid_until)):
            _aware(value, name)
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.granted_at > self.valid_from:
            raise ValueError("grant must be issued no later than valid_from")
        if self.revoked_at is not None:
            _aware(self.revoked_at, "revoked_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reasons: tuple[str, ...]
    via_temporary_grant: bool = False


def authorize(
    session: AuthenticatedSession,
    permission: Permission,
    *,
    now: datetime,
    session_policy: SessionPolicy,
    grants: tuple[TemporaryPermissionGrant, ...] = (),
) -> AuthorizationDecision:
    validation = validate_session(session, now=now, policy=session_policy)
    if not validation.passed:
        return AuthorizationDecision(False, validation.reasons)

    if is_allowed(session.principal, permission):
        return AuthorizationDecision(True, ())

    matching = [g for g in grants if g.principal_id == session.principal.principal_id and g.permission is permission]
    if not matching:
        return AuthorizationDecision(False, ("PERMISSION_DENIED_DEFAULT",))

    active = []
    grant_reasons: list[str] = []
    for grant in matching:
        if now < grant.valid_from:
            grant_reasons.append(f"TEMP_GRANT_NOT_YET_VALID:{grant.grant_id}")
            continue
        if now >= grant.valid_until:
            grant_reasons.append(f"TEMP_GRANT_EXPIRED:{grant.grant_id}")
            continue
        if grant.revoked_at is not None and now >= grant.revoked_at:
            grant_reasons.append(f"TEMP_GRANT_REVOKED:{grant.grant_id}")
            continue
        active.append(grant)
    if len(active) == 1:
        return AuthorizationDecision(True, (), True)
    if len(active) > 1:
        return AuthorizationDecision(False, ("AMBIGUOUS_MULTIPLE_ACTIVE_GRANTS",))
    return AuthorizationDecision(False, tuple(dict.fromkeys(grant_reasons)) or ("PERMISSION_DENIED_DEFAULT",))
