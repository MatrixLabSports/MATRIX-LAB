from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from app.release.canonical import canonical_sha256
from .identity_access import AuthenticatedSession, SessionPolicy, authorize, validate_session
from .rbac import Permission

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class CriticalActionType(str, Enum):
    SECURITY_POLICY_CHANGE = "SECURITY_POLICY_CHANGE"
    SECRET_ROTATION = "SECRET_ROTATION"
    RELEASE_INTEGRATION = "RELEASE_INTEGRATION"
    RISK_POLICY_CHANGE = "RISK_POLICY_CHANGE"
    CONTROLLED_LIVE_SUBMISSION = "CONTROLLED_LIVE_SUBMISSION"


@dataclass(frozen=True)
class CriticalActionRequest:
    action_id: str
    action_type: CriticalActionType
    requested_by: str
    requested_at: datetime
    subject_sha256: str
    justification: str
    ticket_id: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.action_id.strip() or not self.requested_by.strip() or not self.justification.strip() or not self.ticket_id.strip():
            raise ValueError("critical action identifiers, requester, justification and ticket are required")
        _aware(self.requested_at, "requested_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.requested_at:
            raise ValueError("expires_at must be after requested_at")
        if not _HEX64.fullmatch(self.subject_sha256):
            raise ValueError("subject_sha256 must be lowercase SHA-256 hex")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class CriticalApproval:
    approval_id: str
    action_fingerprint: str
    approver_session_fingerprint: str
    approver_principal_id: str
    permission_used: Permission
    approved_at: datetime
    expires_at: datetime
    decision: str = "APPROVE"

    def __post_init__(self) -> None:
        if not self.approval_id.strip() or not self.approver_principal_id.strip():
            raise ValueError("approval_id and approver_principal_id are required")
        if not _HEX64.fullmatch(self.action_fingerprint):
            raise ValueError("action_fingerprint must be SHA-256")
        if not _HEX64.fullmatch(self.approver_session_fingerprint):
            raise ValueError("approver_session_fingerprint must be SHA-256")
        _aware(self.approved_at, "approved_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expires_at must be after approved_at")
        if self.decision != "APPROVE":
            raise ValueError("CriticalApproval only represents APPROVE")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class DualControlPolicy:
    minimum_distinct_approvers: int = 2
    approval_max_age_minutes: int = 30
    required_permissions: tuple[Permission, ...] = (
        Permission.MANAGE_SECURITY_POLICY,
        Permission.SUBMIT_HUMAN_REVIEW,
    )
    require_requester_separation: bool = True

    def __post_init__(self) -> None:
        if self.minimum_distinct_approvers < 2:
            raise ValueError("dual control requires at least two distinct approvers")
        if self.approval_max_age_minutes <= 0:
            raise ValueError("approval_max_age_minutes must be > 0")
        if len(set(self.required_permissions)) != len(self.required_permissions):
            raise ValueError("required_permissions must be unique")


@dataclass(frozen=True)
class DualControlResult:
    passed: bool
    reasons: tuple[str, ...]
    distinct_approvers: int
    approval_fingerprints: tuple[str, ...]
    production_release_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.production_release_enabled:
            raise ValueError("V15 dual control does not authorize production release")
        if self.automatic_wager_execution_enabled:
            raise ValueError("V15 dual control may never enable automatic wagering")
        if self.passed and self.distinct_approvers < 2:
            raise ValueError("passed dual control must have at least two distinct approvers")


def evaluate_dual_control(
    request: CriticalActionRequest,
    approvals: tuple[CriticalApproval, ...],
    sessions: tuple[AuthenticatedSession, ...],
    *,
    now: datetime,
    session_policy: SessionPolicy,
    policy: DualControlPolicy,
) -> DualControlResult:
    _aware(now, "now")
    reasons: list[str] = []
    if now >= request.expires_at:
        reasons.append("CRITICAL_ACTION_REQUEST_EXPIRED")
    if request.requested_at > now + timedelta(minutes=5):
        reasons.append("CRITICAL_ACTION_REQUEST_FROM_FUTURE")

    session_by_fp = {s.fingerprint: s for s in sessions}
    if len(session_by_fp) != len(sessions):
        reasons.append("DUPLICATE_SESSION_EVIDENCE")

    seen_approval_ids: set[str] = set()
    valid: list[CriticalApproval] = []
    for approval in approvals:
        if approval.approval_id in seen_approval_ids:
            reasons.append(f"DUPLICATE_APPROVAL_ID:{approval.approval_id}")
            continue
        seen_approval_ids.add(approval.approval_id)
        if approval.action_fingerprint != request.fingerprint:
            reasons.append(f"APPROVAL_ACTION_MISMATCH:{approval.approval_id}")
            continue
        if approval.approved_at < request.requested_at:
            reasons.append(f"APPROVAL_PRECEDES_REQUEST:{approval.approval_id}")
            continue
        if approval.approved_at > now + timedelta(minutes=5):
            reasons.append(f"APPROVAL_FROM_FUTURE:{approval.approval_id}")
            continue
        if now >= approval.expires_at or now - approval.approved_at > timedelta(minutes=policy.approval_max_age_minutes):
            reasons.append(f"APPROVAL_STALE_OR_EXPIRED:{approval.approval_id}")
            continue
        session = session_by_fp.get(approval.approver_session_fingerprint)
        if session is None:
            reasons.append(f"APPROVER_SESSION_MISSING:{approval.approval_id}")
            continue
        if session.principal.principal_id != approval.approver_principal_id:
            reasons.append(f"APPROVER_IDENTITY_MISMATCH:{approval.approval_id}")
            continue
        sv = validate_session(session, now=now, policy=session_policy)
        if not sv.passed:
            reasons.extend(f"APPROVER_SESSION_INVALID:{approval.approval_id}:{r}" for r in sv.reasons)
            continue
        auth = authorize(session, approval.permission_used, now=now, session_policy=session_policy)
        if not auth.allowed:
            reasons.append(f"APPROVER_PERMISSION_DENIED:{approval.approval_id}:{approval.permission_used.value}")
            continue
        if policy.require_requester_separation and approval.approver_principal_id == request.requested_by:
            reasons.append(f"REQUESTER_MAY_NOT_APPROVE:{approval.approval_id}")
            continue
        valid.append(approval)

    principals = {a.approver_principal_id for a in valid}
    if len(principals) < policy.minimum_distinct_approvers:
        reasons.append("INSUFFICIENT_DISTINCT_APPROVERS")

    used_permissions = {a.permission_used for a in valid}
    for permission in policy.required_permissions:
        if permission not in used_permissions:
            reasons.append(f"REQUIRED_APPROVER_PERMISSION_MISSING:{permission.value}")

    passed = not reasons
    return DualControlResult(
        passed=passed,
        reasons=tuple(dict.fromkeys(reasons)),
        distinct_approvers=len(principals),
        approval_fingerprints=tuple(a.fingerprint for a in valid),
    )
