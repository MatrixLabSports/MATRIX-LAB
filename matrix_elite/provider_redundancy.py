from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .failover import ProviderHealth


@dataclass(frozen=True)
class ProviderReconciliation:
    keys_primary: int
    keys_secondary: int
    keys_overlap: int
    disagreement_count: int
    missing_primary_count: int
    missing_secondary_count: int
    overlap_rate: float
    disagreement_rate_on_overlap: float


def reconcile_provider_snapshots(primary: Mapping[str, str], secondary: Mapping[str, str]) -> ProviderReconciliation:
    p = dict(primary); s = dict(secondary)
    pkeys = set(p); skeys = set(s); overlap = pkeys & skeys; union = pkeys | skeys
    disagree = sum(p[k] != s[k] for k in overlap)
    return ProviderReconciliation(
        keys_primary=len(pkeys),
        keys_secondary=len(skeys),
        keys_overlap=len(overlap),
        disagreement_count=disagree,
        missing_primary_count=len(skeys - pkeys),
        missing_secondary_count=len(pkeys - skeys),
        overlap_rate=len(overlap) / len(union) if union else 1.0,
        disagreement_rate_on_overlap=disagree / len(overlap) if overlap else 1.0,
    )


def governed_failover_with_reconciliation(
    primary: ProviderHealth,
    secondary: ProviderHealth,
    *,
    reconciliation: ProviderReconciliation,
    minimum_secondary_coverage: float,
    minimum_overlap_rate: float,
    maximum_disagreement_rate: float,
    human_approved: bool,
    approval_evidence_sha256: str | None,
) -> str:
    if not 0 <= minimum_secondary_coverage <= 1 or not 0 <= minimum_overlap_rate <= 1 or not 0 <= maximum_disagreement_rate <= 1:
        raise ValueError("FAILOVER_POLICY_INVALID")
    if primary.freshness_ok and primary.rights_ok and primary.schema_ok and primary.coverage >= minimum_secondary_coverage:
        return primary.provider
    if not human_approved:
        raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
    if approval_evidence_sha256 is None or len(approval_evidence_sha256) != 64:
        raise ValueError("FAILOVER_APPROVAL_EVIDENCE_REQUIRED")
    int(approval_evidence_sha256, 16)
    if not (secondary.freshness_ok and secondary.rights_ok and secondary.schema_ok):
        raise ValueError("SECONDARY_PROVIDER_NOT_ADMISSIBLE")
    if secondary.coverage < minimum_secondary_coverage:
        raise ValueError("SECONDARY_COVERAGE_INSUFFICIENT")
    if reconciliation.overlap_rate < minimum_overlap_rate:
        raise ValueError("PROVIDER_OVERLAP_INSUFFICIENT")
    if reconciliation.disagreement_rate_on_overlap > maximum_disagreement_rate:
        raise ValueError("PROVIDER_DISAGREEMENT_TOO_HIGH")
    return secondary.provider
