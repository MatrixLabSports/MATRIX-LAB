# MATRIX V15 — Identity, Access and Dual-Control Policy

Status: **isolated verification only; not production-certified**.

## Core controls

1. Critical actions require a verified authenticated session.
2. Critical actions require phishing-resistant MFA under the V15 reference policy.
3. Authorization is default-deny and RBAC based.
4. Temporary permission grants are explicit, time-bounded, revocable, ticket-linked, and exact-permission scoped.
5. Critical actions require at least two distinct approvers.
6. The requester may not count as an approver when requester separation is enabled.
7. Required approval permissions must come from separate duties (`MANAGE_SECURITY_POLICY` and `SUBMIT_HUMAN_REVIEW` in the V15 reference policy).
8. Every approval is bound to the exact critical-action fingerprint and authenticated-session fingerprint.
9. Approval evidence expires and cannot be replayed for another action.
10. Authenticated audit evidence is bound to the actor session and verified with an Ed25519 key whose purpose includes `audit_authentication`.
11. The audit-event chain detects deletion/reordering/substitution through previous-event SHA-256 linkage.
12. V15 can only mark an action eligible for **human execution review**. It cannot authorize production, model promotion, or automatic wagering.

## Non-claims

Passing V15 does not prove that a real production IdP, hardware security key, MFA policy, SIEM, vault, HSM/KMS, or production trust root is configured. Those require evidence from the actual deployment environment.
