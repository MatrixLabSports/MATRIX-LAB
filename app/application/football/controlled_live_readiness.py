from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
import re
from typing import Any, Mapping

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MODEL_STATES = {"BACKTESTED", "PAPER_TRADING", "CONTROLLED_LIVE"}


def _non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _metric(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric or null")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


@dataclass(frozen=True)
class ControlledLiveEvidence:
    """Evidence required before a football market can enter limited live review.

    This object is deliberately market-specific. Evidence for one market must never
    promote another market.  It also does not authorize transaction execution:
    the platform may only become eligible to surface a controlled, human-reviewed
    live-money decision after every gate has passed.
    """

    market_key: str
    model_version: str
    model_state: str
    protected_test_samples: int
    brier_score: float | None
    calibration_error: float | None
    baseline_dominance_confirmed: bool
    walk_forward_folds: int
    paper_trading_samples: int
    settled_paper_trading_samples: int
    odds_capture_samples: int
    odds_source_authorized: bool
    odds_timestamp_integrity_verified: bool
    reproducibility_verified: bool
    risk_policy_approved: bool
    kill_switch_verified: bool
    human_approval_required: bool
    compliance_review_complete: bool
    unresolved_p0_count: int
    evidence_sha256s: tuple[str, ...] = ()
    closing_odds_samples: int = 0
    closing_odds_integrity_verified: bool = False
    prospective_performance_verified: bool = False
    positive_clv_confirmed: bool = False

    def __post_init__(self) -> None:
        market = self.market_key.strip()
        version = self.model_version.strip()
        state = self.model_state.strip().upper()
        if not market:
            raise ValueError("market_key is required")
        if not version:
            raise ValueError("model_version is required")
        if state not in _ALLOWED_MODEL_STATES:
            raise ValueError("model_state must be BACKTESTED, PAPER_TRADING or CONTROLLED_LIVE")
        object.__setattr__(self, "market_key", market)
        object.__setattr__(self, "model_version", version)
        object.__setattr__(self, "model_state", state)

        for name in (
            "protected_test_samples",
            "walk_forward_folds",
            "paper_trading_samples",
            "settled_paper_trading_samples",
            "odds_capture_samples",
            "unresolved_p0_count",
            "closing_odds_samples",
        ):
            _non_negative_int(name, getattr(self, name))

        if self.settled_paper_trading_samples > self.paper_trading_samples:
            raise ValueError("settled_paper_trading_samples cannot exceed paper_trading_samples")

        object.__setattr__(self, "brier_score", _metric("brier_score", self.brier_score))
        object.__setattr__(self, "calibration_error", _metric("calibration_error", self.calibration_error))

        for field in (
            "baseline_dominance_confirmed",
            "odds_source_authorized",
            "odds_timestamp_integrity_verified",
            "reproducibility_verified",
            "risk_policy_approved",
            "kill_switch_verified",
            "human_approval_required",
            "compliance_review_complete",
            "closing_odds_integrity_verified",
            "prospective_performance_verified",
            "positive_clv_confirmed",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"{field} must be bool")

        normalized_hashes: list[str] = []
        for raw in self.evidence_sha256s:
            if not isinstance(raw, str):
                raise ValueError("evidence_sha256s must contain strings")
            digest = raw.strip().lower()
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError("evidence_sha256s must contain valid SHA-256 digests")
            normalized_hashes.append(digest)
        if len(normalized_hashes) != len(set(normalized_hashes)):
            raise ValueError("evidence_sha256s must not contain duplicates")
        object.__setattr__(self, "evidence_sha256s", tuple(normalized_hashes))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ControlledLiveEvidence":
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        data = dict(payload)
        hashes = data.get("evidence_sha256s", ())
        if isinstance(hashes, list):
            data["evidence_sha256s"] = tuple(hashes)
        return cls(**data)


@dataclass(frozen=True)
class ControlledLivePolicy:
    min_protected_test_samples: int = 500
    max_brier_score: float = 0.22
    max_calibration_error: float = 0.05
    min_walk_forward_folds: int = 5
    min_paper_trading_samples: int = 500
    min_settled_paper_trading_samples: int = 450
    min_odds_capture_samples: int = 500
    min_evidence_artifacts: int = 4
    min_closing_odds_samples: int = 300

    def __post_init__(self) -> None:
        for name in (
            "min_protected_test_samples",
            "min_walk_forward_folds",
            "min_paper_trading_samples",
            "min_settled_paper_trading_samples",
            "min_odds_capture_samples",
            "min_evidence_artifacts",
            "min_closing_odds_samples",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_brier_score", "max_calibration_error"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.min_settled_paper_trading_samples > self.min_paper_trading_samples:
            raise ValueError("settled paper minimum cannot exceed paper trading minimum")


@dataclass(frozen=True)
class ControlledLiveReadiness:
    market_key: str
    model_version: str
    status: str
    controlled_live_review_eligible: bool
    automatic_wager_execution_enabled: bool
    human_approval_required: bool
    blocked_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_controlled_live_readiness(
    evidence: ControlledLiveEvidence,
    *,
    policy: ControlledLivePolicy = ControlledLivePolicy(),
) -> ControlledLiveReadiness:
    reasons: list[str] = []

    if evidence.model_state not in {"PAPER_TRADING", "CONTROLLED_LIVE"}:
        reasons.append("model_not_paper_trading_or_higher")
    if evidence.protected_test_samples < policy.min_protected_test_samples:
        reasons.append("insufficient_protected_test_sample")
    if evidence.brier_score is None:
        reasons.append("brier_score_missing")
    elif evidence.brier_score > policy.max_brier_score:
        reasons.append("brier_score_above_limit")
    if evidence.calibration_error is None:
        reasons.append("calibration_error_missing")
    elif evidence.calibration_error > policy.max_calibration_error:
        reasons.append("calibration_error_above_limit")
    if not evidence.baseline_dominance_confirmed:
        reasons.append("baseline_dominance_not_confirmed")
    if evidence.walk_forward_folds < policy.min_walk_forward_folds:
        reasons.append("insufficient_walk_forward_folds")
    if evidence.paper_trading_samples < policy.min_paper_trading_samples:
        reasons.append("insufficient_paper_trading")
    if evidence.settled_paper_trading_samples < policy.min_settled_paper_trading_samples:
        reasons.append("insufficient_settled_paper_trading")
    if evidence.odds_capture_samples < policy.min_odds_capture_samples:
        reasons.append("insufficient_odds_capture")
    if not evidence.odds_source_authorized:
        reasons.append("odds_source_not_authorized")
    if not evidence.odds_timestamp_integrity_verified:
        reasons.append("odds_timestamp_integrity_not_verified")
    if evidence.closing_odds_samples < policy.min_closing_odds_samples:
        reasons.append("insufficient_closing_odds_capture")
    if not evidence.closing_odds_integrity_verified:
        reasons.append("closing_odds_integrity_not_verified")
    if not evidence.prospective_performance_verified:
        reasons.append("prospective_performance_not_verified")
    if not evidence.positive_clv_confirmed:
        reasons.append("positive_clv_not_confirmed")
    if not evidence.reproducibility_verified:
        reasons.append("reproducibility_not_verified")
    if not evidence.risk_policy_approved:
        reasons.append("risk_policy_not_approved")
    if not evidence.kill_switch_verified:
        reasons.append("kill_switch_not_verified")
    if not evidence.human_approval_required:
        reasons.append("human_approval_gate_missing")
    if not evidence.compliance_review_complete:
        reasons.append("compliance_review_incomplete")
    if evidence.unresolved_p0_count != 0:
        reasons.append("unresolved_p0_items")
    if len(evidence.evidence_sha256s) < policy.min_evidence_artifacts:
        reasons.append("insufficient_verifiable_evidence_artifacts")

    blocked = tuple(dict.fromkeys(reasons))
    eligible = not blocked
    return ControlledLiveReadiness(
        market_key=evidence.market_key,
        model_version=evidence.model_version,
        status="CONTROLLED_LIVE_REVIEW_ELIGIBLE" if eligible else "BLOCKED",
        controlled_live_review_eligible=eligible,
        # Non-negotiable platform invariant: this gate never places or transmits wagers.
        automatic_wager_execution_enabled=False,
        human_approval_required=True,
        blocked_reasons=blocked,
    )


def human_summary(readiness: ControlledLiveReadiness) -> str:
    reasons = ",".join(readiness.blocked_reasons) if readiness.blocked_reasons else "none"
    return "\n".join(
        (
            f"MATRIX_FOOTBALL_CONTROLLED_LIVE_STATUS={readiness.status}",
            f"market_key={readiness.market_key}",
            f"model_version={readiness.model_version}",
            f"controlled_live_review_eligible={str(readiness.controlled_live_review_eligible)}",
            "automatic_wager_execution_enabled=False",
            "human_approval_required=True",
            f"blocked_reasons={reasons}",
        )
    )
