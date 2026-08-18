from __future__ import annotations

from dataclasses import dataclass

from app.research.football.comparison import PairedModelComparison
from app.research.football.quality import DatasetQualityReport
from app.research.football.validation import BinaryModelEvaluation, ModelPromotionPolicy


@dataclass(frozen=True)
class ResearchPromotionEvidence:
    dataset_quality: DatasetQualityReport
    test_evaluation: BinaryModelEvaluation
    baseline_comparison: PairedModelComparison
    paper_trading_samples: int = 0
    odds_validation_complete: bool = False
    reproducibility_verified: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.paper_trading_samples, bool) or not isinstance(self.paper_trading_samples, int) or self.paper_trading_samples < 0:
            raise ValueError("paper_trading_samples must be a non-negative integer")


@dataclass(frozen=True)
class ResearchPromotionGate:
    model_policy: ModelPromotionPolicy = ModelPromotionPolicy()
    min_paper_trading_samples: int = 500
    require_brier_baseline_dominance: bool = True
    require_logloss_baseline_dominance: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.min_paper_trading_samples, bool) or not isinstance(self.min_paper_trading_samples, int) or self.min_paper_trading_samples < 0:
            raise ValueError("min_paper_trading_samples must be non-negative")

    def reasons_blocked(self, evidence: ResearchPromotionEvidence) -> tuple[str, ...]:
        reasons: list[str] = []
        if not evidence.dataset_quality.passed:
            reasons.append("dataset_quality_gate_failed")
        reasons.extend(self.model_policy.reasons_not_promotable(evidence.test_evaluation))
        if self.require_brier_baseline_dominance and not evidence.baseline_comparison.candidate_beats_baseline_with_brier_confidence:
            reasons.append("candidate_does_not_beat_baseline_on_brier_with_confidence")
        if self.require_logloss_baseline_dominance and not evidence.baseline_comparison.candidate_beats_baseline_with_logloss_confidence:
            reasons.append("candidate_does_not_beat_baseline_on_logloss_with_confidence")
        if evidence.paper_trading_samples < self.min_paper_trading_samples:
            reasons.append("insufficient_paper_trading")
        if not evidence.odds_validation_complete:
            reasons.append("odds_ev_validation_missing")
        if not evidence.reproducibility_verified:
            reasons.append("reproducibility_not_verified")
        return tuple(dict.fromkeys(reasons))

    def live_money_eligible(self, evidence: ResearchPromotionEvidence) -> bool:
        return not self.reasons_blocked(evidence)
