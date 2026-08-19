from __future__ import annotations

from .threat_model import Severity, Threat


def matrix_security_baseline() -> tuple[Threat, ...]:
    return (
        Threat("SEC-001", "provider credentials", "process/environment", "credential disclosure through source code or logs", Severity.CRITICAL, ("environment secret references", "secret scanning", "log redaction")),
        Threat("SEC-002", "prediction/audit evidence", "application/storage", "retroactive tampering with decision evidence", Severity.CRITICAL, ("append-only hash chain", "externalized integrity anchor")),
        Threat("SEC-003", "runtime configuration", "deployment/config", "unauthorized configuration modification", Severity.HIGH, ("canonical config fingerprint", "change review")),
        Threat("SEC-004", "dependencies", "supply chain", "vulnerable or substituted dependency artifact", Severity.HIGH, ("exact version+hash lock", "fresh vulnerability scan evidence")),
        Threat("SEC-005", "operator capabilities", "user/application", "privilege escalation", Severity.HIGH, ("default-deny RBAC", "least privilege", "access logging")),
        Threat("SEC-006", "production runtime", "development/production", "development credentials or artifacts reach production", Severity.HIGH, ("environment separation", "promotion gate")),
        Threat("SEC-007", "availability", "provider/network", "provider outage degrades decision quality", Severity.HIGH, ("fail-closed freshness gate", "authorized redundancy policy")),
        Threat("SEC-008", "backups", "storage/recovery", "backup corruption discovered only during incident", Severity.HIGH, ("restore verification", "integrity manifests", "recovery drills")),
        Threat("SEC-009", "human review", "application/operator", "replay of stale authorization", Severity.HIGH, ("expiry", "single-use approval fingerprint", "exact quote binding")),
        Threat("SEC-010", "personal/account data", "application/logging", "excessive sensitive data retention", Severity.MEDIUM, ("data minimization", "retention policy")),
    )
