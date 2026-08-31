from __future__ import annotations

from dataclasses import dataclass

from .uncertainty import BlockBootstrapComparison


def _sha(value: str, name: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{name}_REQUIRED")
    int(value, 16)


@dataclass(frozen=True)
class OOSPromotionEvidence:
    sport: str
    market: str
    pit_snapshot_sha256: str
    identity_manifest_sha256: str
    model_version: str
    feature_version: str
    fold_count: int
    final_holdout_n: int
    final_holdout_untouched: bool
    model_ece: float
    max_calibration_gap: float
    block_bootstrap: BlockBootstrapComparison
    segment_positive_fraction: float
    segment_eligible_count: int
    leakage_audit_passed: bool
    market_baseline_present: bool
    empirical_baseline_present: bool

    def __post_init__(self) -> None:
        _sha(self.pit_snapshot_sha256, "PIT_SNAPSHOT_SHA256")
        _sha(self.identity_manifest_sha256, "IDENTITY_MANIFEST_SHA256")
        if not self.sport.strip() or not self.market.strip() or not self.model_version.strip() or not self.feature_version.strip():
            raise ValueError("OOS_IDENTITY_METADATA_REQUIRED")
        if self.fold_count < 1 or self.final_holdout_n < 20:
            raise ValueError("OOS_SAMPLE_EVIDENCE_INSUFFICIENT")
        if not 0 <= self.model_ece <= 1 or not 0 <= self.max_calibration_gap <= 1:
            raise ValueError("CALIBRATION_METRIC_OUT_OF_RANGE")
        if not 0 <= self.segment_positive_fraction <= 1 or self.segment_eligible_count < 1:
            raise ValueError("SEGMENT_EVIDENCE_INVALID")


def oos_promotion_gate(
    evidence: OOSPromotionEvidence,
    *,
    max_ece: float,
    max_calibration_gap: float,
    min_segment_positive_fraction: float = 0.75,
    require_ci_above_zero: bool = True,
) -> bool:
    if not evidence.final_holdout_untouched or not evidence.leakage_audit_passed:
        return False
    if not evidence.market_baseline_present or not evidence.empirical_baseline_present:
        return False
    if evidence.model_ece > max_ece or evidence.max_calibration_gap > max_calibration_gap:
        return False
    if evidence.segment_positive_fraction < min_segment_positive_fraction:
        return False
    b = evidence.block_bootstrap
    if b.brier_improvement <= 0 or b.log_loss_improvement <= 0:
        return False
    if require_ci_above_zero and (b.brier_ci95[0] <= 0 or b.log_loss_ci95[0] <= 0):
        return False
    return True
