from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.release.canonical import canonical_sha256
from app.security.attestation import AttestationPayload, TrustedKey, TrustStore, public_key_b64, sign_attestation
from app.security.audit_authentication import (
    AuthenticatedAuditEvent,
    SignedAuditEvidence,
    verify_audit_chain,
    verify_audit_evidence,
)
from app.security.critical_action_gate import CriticalActionGateStatus, evaluate_critical_action_gate
from app.security.dual_control import (
    CriticalActionRequest,
    CriticalActionType,
    CriticalApproval,
    DualControlPolicy,
    evaluate_dual_control,
)
from app.security.identity_access import (
    AuthenticatedSession,
    AuthenticationStrength,
    SessionPolicy,
    TemporaryPermissionGrant,
    authorize,
    validate_session,
)
from app.security.rbac import Permission, Principal

NOW = datetime(2026, 8, 18, 23, 42, tzinfo=timezone.utc)
H64 = "a" * 64
H64B = "b" * 64
SESSION_POLICY = SessionPolicy(
    max_session_age_minutes=60,
    required_strength=AuthenticationStrength.PHISHING_RESISTANT_MFA,
)


def principal(pid: str, role: str) -> Principal:
    return Principal(pid, (role,))


def session(
    pid: str,
    role: str,
    *,
    sid: str | None = None,
    strength: AuthenticationStrength = AuthenticationStrength.PHISHING_RESISTANT_MFA,
    verified: bool = True,
    authenticated_at: datetime | None = None,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> AuthenticatedSession:
    return AuthenticatedSession(
        session_id=sid or f"session-{pid}",
        principal=principal(pid, role),
        identity_provider="matrix-idp-contract",
        authenticated_at=authenticated_at or NOW - timedelta(minutes=5),
        expires_at=expires_at or NOW + timedelta(minutes=30),
        auth_strength=strength,
        identity_verified=verified,
        revoked_at=revoked_at,
    )


def request(*, requester: str = "requester", expires_at: datetime | None = None) -> CriticalActionRequest:
    return CriticalActionRequest(
        action_id="action-001",
        action_type=CriticalActionType.RELEASE_INTEGRATION,
        requested_by=requester,
        requested_at=NOW - timedelta(minutes=4),
        subject_sha256=H64,
        justification="Integrate a release that passed the preceding review gates.",
        ticket_id="SEC-2026-001",
        expires_at=expires_at or NOW + timedelta(minutes=20),
    )


def approval(req: CriticalActionRequest, sess: AuthenticatedSession, permission: Permission, *, aid: str, approved_at=None, expires_at=None, action_fp=None):
    return CriticalApproval(
        approval_id=aid,
        action_fingerprint=action_fp or req.fingerprint,
        approver_session_fingerprint=sess.fingerprint,
        approver_principal_id=sess.principal.principal_id,
        permission_used=permission,
        approved_at=approved_at or NOW - timedelta(minutes=2),
        expires_at=expires_at or NOW + timedelta(minutes=10),
    )


def valid_dual_control(req: CriticalActionRequest | None = None):
    req = req or request()
    sec = session("security-approver", "security_admin")
    op = session("operations-approver", "operator")
    approvals = (
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="approval-security"),
        approval(req, op, Permission.SUBMIT_HUMAN_REVIEW, aid="approval-operator"),
    )
    return req, sec, op, approvals


def test_session_strong_identity_passes():
    result = validate_session(session("a-user", "analyst"), now=NOW, policy=SESSION_POLICY)
    assert result.passed is True


def test_unverified_identity_blocks():
    result = validate_session(session("a-user", "analyst", verified=False), now=NOW, policy=SESSION_POLICY)
    assert "IDENTITY_NOT_VERIFIED" in result.reasons


def test_password_only_blocks_critical_session_policy():
    result = validate_session(session("a-user", "analyst", strength=AuthenticationStrength.PASSWORD_ONLY), now=NOW, policy=SESSION_POLICY)
    assert "AUTHENTICATION_STRENGTH_INSUFFICIENT" in result.reasons


def test_non_phishing_resistant_mfa_blocks_when_policy_requires_strongest():
    result = validate_session(session("a-user", "analyst", strength=AuthenticationStrength.MFA), now=NOW, policy=SESSION_POLICY)
    assert "AUTHENTICATION_STRENGTH_INSUFFICIENT" in result.reasons


def test_expired_session_blocks():
    result = validate_session(session("a-user", "analyst", expires_at=NOW), now=NOW, policy=SESSION_POLICY)
    assert "SESSION_EXPIRED" in result.reasons


def test_revoked_session_blocks():
    result = validate_session(session("a-user", "analyst", revoked_at=NOW - timedelta(seconds=1)), now=NOW, policy=SESSION_POLICY)
    assert "SESSION_REVOKED" in result.reasons


def test_old_session_blocks_even_if_expiry_is_later():
    s = session("a-user", "analyst", authenticated_at=NOW - timedelta(hours=2), expires_at=NOW + timedelta(hours=1))
    result = validate_session(s, now=NOW, policy=SESSION_POLICY)
    assert "SESSION_TOO_OLD" in result.reasons


def test_future_authentication_blocks():
    s = session("a-user", "analyst", authenticated_at=NOW + timedelta(hours=1), expires_at=NOW + timedelta(hours=2))
    result = validate_session(s, now=NOW, policy=SESSION_POLICY)
    assert "AUTHENTICATION_FROM_FUTURE" in result.reasons


def test_role_authorization_uses_default_deny():
    s = session("reader-user", "reader")
    result = authorize(s, Permission.MANAGE_SECURITY_POLICY, now=NOW, session_policy=SESSION_POLICY)
    assert result.allowed is False
    assert result.reasons == ("PERMISSION_DENIED_DEFAULT",)


def test_existing_role_permission_is_allowed():
    s = session("security-user", "security_admin")
    assert authorize(s, Permission.MANAGE_SECURITY_POLICY, now=NOW, session_policy=SESSION_POLICY).allowed is True


def grant(*, revoked_at=None, valid_from=None, valid_until=None):
    return TemporaryPermissionGrant(
        grant_id="grant-001",
        principal_id="reader-user",
        permission=Permission.VIEW_AUDIT,
        granted_by="security-admin",
        granted_at=NOW - timedelta(minutes=10),
        valid_from=valid_from or NOW - timedelta(minutes=5),
        valid_until=valid_until or NOW + timedelta(minutes=5),
        reason="Temporary incident review",
        ticket_id="INC-42",
        revoked_at=revoked_at,
    )


def test_temporary_permission_grant_can_authorize_exact_permission():
    result = authorize(session("reader-user", "reader"), Permission.VIEW_AUDIT, now=NOW, session_policy=SESSION_POLICY, grants=(grant(),))
    assert result.allowed is True
    assert result.via_temporary_grant is True


def test_temporary_grant_does_not_grant_other_permissions():
    result = authorize(session("reader-user", "reader"), Permission.MANAGE_SECURITY_POLICY, now=NOW, session_policy=SESSION_POLICY, grants=(grant(),))
    assert result.allowed is False


def test_expired_temporary_grant_blocks():
    g = grant(valid_from=NOW - timedelta(minutes=10), valid_until=NOW - timedelta(seconds=1))
    result = authorize(session("reader-user", "reader"), Permission.VIEW_AUDIT, now=NOW, session_policy=SESSION_POLICY, grants=(g,))
    assert result.allowed is False
    assert any(x.startswith("TEMP_GRANT_EXPIRED") for x in result.reasons)


def test_revoked_temporary_grant_blocks():
    result = authorize(session("reader-user", "reader"), Permission.VIEW_AUDIT, now=NOW, session_policy=SESSION_POLICY, grants=(grant(revoked_at=NOW-timedelta(seconds=1)),))
    assert result.allowed is False
    assert any(x.startswith("TEMP_GRANT_REVOKED") for x in result.reasons)


def test_multiple_active_grants_fail_closed():
    g2 = replace(grant(), grant_id="grant-002")
    result = authorize(session("reader-user", "reader"), Permission.VIEW_AUDIT, now=NOW, session_policy=SESSION_POLICY, grants=(grant(), g2))
    assert result.allowed is False
    assert "AMBIGUOUS_MULTIPLE_ACTIVE_GRANTS" in result.reasons


def test_valid_dual_control_passes():
    req, sec, op, approvals = valid_dual_control()
    result = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert result.passed is True
    assert result.distinct_approvers == 2
    assert result.production_release_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_same_person_cannot_satisfy_dual_control_twice():
    req = request()
    sec = session("security-approver", "security_admin")
    approvals = (
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (sec,), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy(required_permissions=(Permission.MANAGE_SECURITY_POLICY,)))
    assert result.passed is False
    assert "INSUFFICIENT_DISTINCT_APPROVERS" in result.reasons


def test_requester_cannot_approve_own_critical_action():
    req = request(requester="security-approver")
    _, sec, op, _ = valid_dual_control(req)
    approvals = (
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, op, Permission.SUBMIT_HUMAN_REVIEW, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert any(x.startswith("REQUESTER_MAY_NOT_APPROVE") for x in result.reasons)


def test_approval_for_other_action_is_rejected():
    req, sec, op, approvals = valid_dual_control()
    bad = replace(approvals[0], action_fingerprint=H64B)
    result = evaluate_dual_control(req, (bad, approvals[1]), (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert any(x.startswith("APPROVAL_ACTION_MISMATCH") for x in result.reasons)


def test_stale_approval_is_rejected():
    req, sec, op, approvals = valid_dual_control()
    stale = replace(approvals[0], approved_at=NOW - timedelta(minutes=3), expires_at=NOW + timedelta(minutes=1))
    result = evaluate_dual_control(
        req,
        (stale, approvals[1]),
        (sec, op),
        now=NOW,
        session_policy=SESSION_POLICY,
        policy=DualControlPolicy(approval_max_age_minutes=2),
    )
    assert any(x.startswith("APPROVAL_STALE_OR_EXPIRED") for x in result.reasons)


def test_revoked_approver_session_is_rejected():
    req = request()
    sec = session("security-approver", "security_admin", revoked_at=NOW - timedelta(seconds=1))
    op = session("operations-approver", "operator")
    approvals = (
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, op, Permission.SUBMIT_HUMAN_REVIEW, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert any("SESSION_REVOKED" in x for x in result.reasons)


def test_missing_required_separation_of_duties_permission_blocks():
    req = request()
    sec1 = session("security-one", "security_admin")
    sec2 = session("security-two", "security_admin")
    approvals = (
        approval(req, sec1, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, sec2, Permission.MANAGE_SECURITY_POLICY, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (sec1, sec2), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert "REQUIRED_APPROVER_PERMISSION_MISSING:submit_human_review" in result.reasons


def test_approver_permission_must_actually_belong_to_role():
    req = request()
    reader = session("reader-approver", "reader")
    op = session("operations-approver", "operator")
    approvals = (
        approval(req, reader, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, op, Permission.SUBMIT_HUMAN_REVIEW, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (reader, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert any(x.startswith("APPROVER_PERMISSION_DENIED") for x in result.reasons)


def test_expired_critical_request_blocks_even_with_valid_approvals():
    req = request(expires_at=NOW - timedelta(seconds=1))
    # construct approvals relative to the now-expired request; dataclass permits it because expiry was after request time
    sec = session("security-approver", "security_admin")
    op = session("operations-approver", "operator")
    approvals = (
        approval(req, sec, Permission.MANAGE_SECURITY_POLICY, aid="a1"),
        approval(req, op, Permission.SUBMIT_HUMAN_REVIEW, aid="a2"),
    )
    result = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    assert "CRITICAL_ACTION_REQUEST_EXPIRED" in result.reasons


def audit_key(*, key_id="audit-key", purpose="audit_authentication", production=False):
    private = Ed25519PrivateKey.generate()
    trusted = TrustedKey(
        key_id=key_id,
        issuer="matrix-audit-isolated",
        public_key_b64=public_key_b64(private),
        purposes=(purpose,),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        production_trusted=production,
    )
    return private, trusted


def audit_event(sess: AuthenticatedSession, *, event_id="evt-1", previous=None, action="APPROVE_RELEASE", details=H64B, occurred_at=None):
    return AuthenticatedAuditEvent(
        event_id=event_id,
        actor_principal_id=sess.principal.principal_id,
        actor_session_fingerprint=sess.fingerprint,
        action=action,
        resource="release:isolated-v15",
        occurred_at=occurred_at or NOW - timedelta(minutes=1),
        outcome="ALLOW",
        details_sha256=details,
        previous_event_sha256=previous,
    )


def signed_audit(sess: AuthenticatedSession, private: Ed25519PrivateKey, key_id: str, *, event=None):
    event = event or audit_event(sess)
    payload = AttestationPayload(
        subject_sha256=event.fingerprint,
        predicate_type="matrix/audit-authentication",
        predicate_sha256=event.details_sha256,
        issuer="matrix-audit-isolated",
        key_id=key_id,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=20),
        nonce=f"nonce-{event.event_id}",
    )
    return SignedAuditEvidence(event, sign_attestation(private, payload))


def test_signed_audit_evidence_passes():
    s = session("security-approver", "security_admin")
    private, trusted = audit_key()
    result = verify_audit_evidence(signed_audit(s, private, trusted.key_id), trust_store=TrustStore({trusted.key_id: trusted}), actor_session=s, now=NOW, session_policy=SESSION_POLICY)
    assert result.passed is True


def test_audit_tampering_is_detected():
    s = session("security-approver", "security_admin")
    private, trusted = audit_key()
    evidence = signed_audit(s, private, trusted.key_id)
    tampered = SignedAuditEvidence(replace(evidence.event, action="ALTER_POLICY"), evidence.attestation)
    result = verify_audit_evidence(tampered, trust_store=TrustStore({trusted.key_id: trusted}), actor_session=s, now=NOW, session_policy=SESSION_POLICY)
    assert any("ATTESTATION_SUBJECT_MISMATCH" in x for x in result.reasons)


def test_audit_session_binding_is_enforced():
    s = session("security-approver", "security_admin")
    other = session("other-security", "security_admin")
    private, trusted = audit_key()
    result = verify_audit_evidence(signed_audit(s, private, trusted.key_id), trust_store=TrustStore({trusted.key_id: trusted}), actor_session=other, now=NOW, session_policy=SESSION_POLICY)
    assert "AUDIT_ACTOR_IDENTITY_MISMATCH" in result.reasons
    assert "AUDIT_SESSION_FINGERPRINT_MISMATCH" in result.reasons


def test_wrong_key_purpose_blocks_audit_authentication():
    s = session("security-approver", "security_admin")
    private, trusted = audit_key(purpose="release_attestation")
    result = verify_audit_evidence(signed_audit(s, private, trusted.key_id), trust_store=TrustStore({trusted.key_id: trusted}), actor_session=s, now=NOW, session_policy=SESSION_POLICY)
    assert any("KEY_PURPOSE_NOT_ALLOWED" in x for x in result.reasons)


def test_isolated_audit_key_does_not_satisfy_production_trust():
    s = session("security-approver", "security_admin")
    private, trusted = audit_key(production=False)
    result = verify_audit_evidence(signed_audit(s, private, trusted.key_id), trust_store=TrustStore({trusted.key_id: trusted}), actor_session=s, now=NOW, session_policy=SESSION_POLICY, require_production_trust=True)
    assert any("KEY_NOT_PRODUCTION_TRUSTED" in x for x in result.reasons)


def test_future_audit_event_blocks():
    s = session("security-approver", "security_admin")
    private, trusted = audit_key()
    ev = audit_event(s, occurred_at=NOW + timedelta(hours=1))
    result = verify_audit_evidence(signed_audit(s, private, trusted.key_id, event=ev), trust_store=TrustStore({trusted.key_id: trusted}), actor_session=s, now=NOW, session_policy=SESSION_POLICY)
    assert "AUDIT_EVENT_FROM_FUTURE" in result.reasons


def test_audit_chain_passes_for_correct_hash_links():
    s = session("security-approver", "security_admin")
    one = audit_event(s, event_id="evt-1")
    two = audit_event(s, event_id="evt-2", previous=one.fingerprint, action="SECOND_ACTION")
    assert verify_audit_chain((one, two)).passed is True


def test_audit_chain_break_is_detected():
    s = session("security-approver", "security_admin")
    one = audit_event(s, event_id="evt-1")
    two = audit_event(s, event_id="evt-2", previous=H64, action="SECOND_ACTION")
    result = verify_audit_chain((one, two))
    assert "AUDIT_CHAIN_BROKEN:evt-2" in result.reasons


def test_duplicate_audit_event_id_is_detected():
    s = session("security-approver", "security_admin")
    one = audit_event(s, event_id="evt-1")
    two = audit_event(s, event_id="evt-1", previous=one.fingerprint, action="SECOND_ACTION")
    result = verify_audit_chain((one, two))
    assert "DUPLICATE_AUDIT_EVENT_ID:evt-1" in result.reasons


def test_critical_action_gate_passes_only_to_human_execution_review():
    req, sec, op, approvals = valid_dual_control()
    dual = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())

    p1, k1 = audit_key(key_id="audit-key-1")
    p2, k2 = audit_key(key_id="audit-key-2")
    e1 = signed_audit(sec, p1, k1.key_id, event=audit_event(sec, event_id="evt-sec"))
    e2 = signed_audit(op, p2, k2.key_id, event=audit_event(op, event_id="evt-op"))
    store = TrustStore({k1.key_id: k1, k2.key_id: k2})
    a1 = verify_audit_evidence(e1, trust_store=store, actor_session=sec, now=NOW, session_policy=SESSION_POLICY)
    a2 = verify_audit_evidence(e2, trust_store=store, actor_session=op, now=NOW, session_policy=SESSION_POLICY)

    result = evaluate_critical_action_gate(dual, (a1, a2))
    assert result.status is CriticalActionGateStatus.PASS
    assert result.eligible_for_human_execution_review is True
    assert result.production_release_enabled is False
    assert result.automatic_model_promotion_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_critical_action_gate_blocks_if_one_audit_attestation_fails():
    req, sec, op, approvals = valid_dual_control()
    dual = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    p1, k1 = audit_key(key_id="audit-key-1")
    good = verify_audit_evidence(signed_audit(sec, p1, k1.key_id), trust_store=TrustStore({k1.key_id: k1}), actor_session=sec, now=NOW, session_policy=SESSION_POLICY)
    bad = replace(good, passed=False, reasons=("SIMULATED_INVALID_AUDIT_EVIDENCE",))
    result = evaluate_critical_action_gate(dual, (good, bad))
    assert result.status is CriticalActionGateStatus.BLOCK
    assert result.eligible_for_human_execution_review is False


def test_critical_action_gate_requires_two_authenticated_audit_records():
    req, sec, op, approvals = valid_dual_control()
    dual = evaluate_dual_control(req, approvals, (sec, op), now=NOW, session_policy=SESSION_POLICY, policy=DualControlPolicy())
    p1, k1 = audit_key(key_id="audit-key-1")
    good = verify_audit_evidence(signed_audit(sec, p1, k1.key_id), trust_store=TrustStore({k1.key_id: k1}), actor_session=sec, now=NOW, session_policy=SESSION_POLICY)
    result = evaluate_critical_action_gate(dual, (good,))
    assert result.status is CriticalActionGateStatus.BLOCK
    assert "INSUFFICIENT_AUTHENTICATED_AUDIT_EVIDENCE" in result.reasons


def test_v15_result_objects_reject_automatic_wager_enablement():
    from app.security.dual_control import DualControlResult
    from app.security.critical_action_gate import CriticalActionGateResult

    with pytest.raises(ValueError):
        DualControlResult(True, (), 2, (H64, H64B), automatic_wager_execution_enabled=True)
    with pytest.raises(ValueError):
        CriticalActionGateResult(CriticalActionGateStatus.PASS, (), True, automatic_wager_execution_enabled=True)
