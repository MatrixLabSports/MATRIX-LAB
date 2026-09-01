from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    return value


def _canonical_sha(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RollbackEvidence:
    primary_rights_pass: bool
    secondary_rights_pass: bool
    schema_compatible: bool
    identity_reconciled: bool
    consecutive_reconciliation_samples: int
    primary_stability_seconds: int
    human_approval_pass: bool
    drill_pass: bool
    drill_evidence_sha256: str
    recovery_backfill_complete: bool
    primary_watermark_caught_up: bool
    unreconciled_gap_count: int
    data_loss_events: int
    open_incident_count: int

    def __post_init__(self) -> None:
        for name in ("consecutive_reconciliation_samples", "primary_stability_seconds", "unreconciled_gap_count", "data_loss_events", "open_incident_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name.upper()}_NONNEGATIVE_INTEGER_REQUIRED")
        _sha(self.drill_evidence_sha256, "drill_evidence")


@dataclass(frozen=True)
class ProviderFailoverRollbackPlan:
    version: str
    primary_provider: str
    secondary_provider: str
    environment: str
    minimum_primary_stability_seconds: int
    minimum_reconciliation_samples: int
    primary_rights_profile_version: str
    secondary_rights_profile_version: str
    schema_compatibility_contract_version: str
    identity_reconciliation_contract_version: str
    human_approval_policy_version: str
    automatic_switch_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.version.startswith("MATRIX-FAILOVER-ROLLBACK-R2/"):
            raise ValueError("ROLLBACK_VERSION_INVALID")
        for name in ("primary_provider", "secondary_provider"):
            _required(getattr(self, name), name)
        if self.primary_provider == self.secondary_provider:
            raise ValueError("PROVIDERS_MUST_DIFFER")
        if self.environment not in {"STAGING", "SHADOW"}:
            raise ValueError("ENVIRONMENT_MUST_BE_STAGING_OR_SHADOW")
        if isinstance(self.minimum_primary_stability_seconds, bool) or self.minimum_primary_stability_seconds <= 0:
            raise ValueError("POSITIVE_PRIMARY_STABILITY_REQUIRED")
        if isinstance(self.minimum_reconciliation_samples, bool) or self.minimum_reconciliation_samples <= 0:
            raise ValueError("POSITIVE_RECONCILIATION_SAMPLE_REQUIREMENT")
        if self.automatic_switch_allowed:
            raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
        for name in (
            "primary_rights_profile_version", "secondary_rights_profile_version",
            "schema_compatibility_contract_version", "identity_reconciliation_contract_version",
            "human_approval_policy_version",
        ):
            _required(getattr(self, name), name)
        expected = f"MATRIX-FAILOVER-ROLLBACK-R2/{self.primary_provider}__{self.secondary_provider}__{self.environment.lower()}"
        if self.version != expected:
            raise ValueError("ROLLBACK_VERSION_IDENTITY_MISMATCH")

    def payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "primary_provider": self.primary_provider,
            "secondary_provider": self.secondary_provider,
            "environment": self.environment,
            "minimum_primary_stability_seconds": self.minimum_primary_stability_seconds,
            "minimum_reconciliation_samples": self.minimum_reconciliation_samples,
            "primary_rights_profile_version": self.primary_rights_profile_version,
            "secondary_rights_profile_version": self.secondary_rights_profile_version,
            "schema_compatibility_contract_version": self.schema_compatibility_contract_version,
            "identity_reconciliation_contract_version": self.identity_reconciliation_contract_version,
            "human_approval_policy_version": self.human_approval_policy_version,
            "automatic_switch_allowed": False,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha(self.payload())

    def evaluate(self, evidence: RollbackEvidence) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        checks = (
            (evidence.primary_rights_pass, "PRIMARY_RIGHTS_NOT_ADMISSIBLE"),
            (evidence.secondary_rights_pass, "SECONDARY_RIGHTS_NOT_ADMISSIBLE"),
            (evidence.schema_compatible, "SCHEMA_NOT_COMPATIBLE"),
            (evidence.identity_reconciled, "IDENTITY_NOT_RECONCILED"),
            (evidence.human_approval_pass, "HUMAN_APPROVAL_REQUIRED"),
            (evidence.drill_pass, "RECENT_DRILL_REQUIRED"),
            (evidence.recovery_backfill_complete, "RECOVERY_BACKFILL_INCOMPLETE"),
            (evidence.primary_watermark_caught_up, "PRIMARY_WATERMARK_NOT_CAUGHT_UP"),
        )
        for passed, reason in checks:
            if not passed:
                reasons.append(reason)
        if evidence.consecutive_reconciliation_samples < self.minimum_reconciliation_samples:
            reasons.append("RECONCILIATION_WINDOW_INSUFFICIENT")
        if evidence.primary_stability_seconds < self.minimum_primary_stability_seconds:
            reasons.append("PRIMARY_STABILITY_WINDOW_INSUFFICIENT")
        if evidence.unreconciled_gap_count != 0:
            reasons.append("UNRECONCILED_GAPS_PRESENT")
        if evidence.data_loss_events != 0:
            reasons.append("DATA_LOSS_DETECTED")
        if evidence.open_incident_count != 0:
            reasons.append("OPEN_INCIDENTS_BLOCK_ROLLBACK")
        return (not reasons, tuple(reasons))
