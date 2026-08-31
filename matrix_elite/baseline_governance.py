from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .baselines import MARKETS_BY_SPORT, BaselineInputEvidence, require_registered_market


@dataclass(frozen=True)
class MarketBaselinePolicy:
    sport: str
    market: str
    task_type: str
    minimum_train_n: int
    minimum_validation_n: int
    requires_market_baseline: bool = True
    requires_empirical_baseline: bool = True
    shared_cross_market_model_allowed: bool = False

    def __post_init__(self) -> None:
        require_registered_market(self.sport, self.market)
        if self.task_type not in {"BINARY", "MULTICLASS", "COUNT_DERIVED_BINARY"}:
            raise ValueError("BASELINE_TASK_TYPE_INVALID")
        if self.minimum_train_n < 20 or self.minimum_validation_n < 20:
            raise ValueError("BASELINE_MINIMUM_SAMPLE_TOO_SMALL")
        if self.shared_cross_market_model_allowed:
            raise ValueError("SHARED_CROSS_MARKET_MODEL_FORBIDDEN")


def default_baseline_policies() -> dict[tuple[str, str], MarketBaselinePolicy]:
    out: dict[tuple[str, str], MarketBaselinePolicy] = {}
    for market in sorted(MARKETS_BY_SPORT["football"]):
        task = "MULTICLASS" if market == "1X2" else "BINARY"
        out[("football", market)] = MarketBaselinePolicy("football", market, task, 200, 50)
    for market in sorted(MARKETS_BY_SPORT["tennis"]):
        out[("tennis", market)] = MarketBaselinePolicy("tennis", market, "BINARY", 200, 50)
    return out


def validate_baseline_evidence(
    evidence: BaselineInputEvidence,
    *,
    policies: Mapping[tuple[str, str], MarketBaselinePolicy] | None = None,
) -> MarketBaselinePolicy:
    policies = dict(policies or default_baseline_policies())
    key = (evidence.sport, evidence.market)
    if key not in policies:
        raise ValueError("BASELINE_POLICY_NOT_FOUND")
    policy = policies[key]
    if evidence.train_n < policy.minimum_train_n or evidence.validation_n < policy.minimum_validation_n:
        raise ValueError("BASELINE_SAMPLE_SIZE_GATE_FAILED")
    return policy
