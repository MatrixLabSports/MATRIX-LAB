from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import Any, Mapping


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _positive_float(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return number


def _non_negative_float(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and >= 0")
    return number


def _probability(name: str, value: float) -> float:
    number = _non_negative_float(name, value)
    if number > 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return number


def _required_text(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


@dataclass(frozen=True)
class FootballRiskPolicy:
    """Fail-closed capital and execution policy for controlled live review.

    Values are intentionally conservative defaults. They are governance limits,
    not profitability claims. The policy never transmits a wager.
    """

    fractional_kelly: float = 0.25
    max_stake_fraction_bankroll: float = 0.005
    max_daily_exposure_fraction_bankroll: float = 0.02
    max_market_exposure_fraction_bankroll: float = 0.01
    max_total_open_exposure_fraction_bankroll: float = 0.02
    daily_drawdown_kill_fraction: float = 0.03
    peak_drawdown_kill_fraction: float = 0.08
    max_prematch_quote_age_seconds: int = 30
    max_live_quote_age_seconds: int = 5
    approval_ttl_seconds: int = 30
    min_decimal_odds: float = 1.20
    max_decimal_odds: float = 6.00

    def __post_init__(self) -> None:
        for name in (
            "fractional_kelly",
            "max_stake_fraction_bankroll",
            "max_daily_exposure_fraction_bankroll",
            "max_market_exposure_fraction_bankroll",
            "max_total_open_exposure_fraction_bankroll",
            "daily_drawdown_kill_fraction",
            "peak_drawdown_kill_fraction",
        ):
            value = _probability(name, getattr(self, name))
            if value == 0:
                raise ValueError(f"{name} must be > 0")
        if self.fractional_kelly > 0.5:
            raise ValueError("fractional_kelly cannot exceed 0.5")
        for name in (
            "max_prematch_quote_age_seconds",
            "max_live_quote_age_seconds",
            "approval_ttl_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        min_odds = _positive_float("min_decimal_odds", self.min_decimal_odds)
        max_odds = _positive_float("max_decimal_odds", self.max_decimal_odds)
        if min_odds >= max_odds:
            raise ValueError("min_decimal_odds must be below max_decimal_odds")


@dataclass(frozen=True)
class FootballCapitalState:
    bankroll: float
    day_start_bankroll: float
    peak_bankroll: float
    daily_exposure: float
    market_exposure: float
    total_open_exposure: float

    def __post_init__(self) -> None:
        for name in ("bankroll", "day_start_bankroll", "peak_bankroll"):
            _positive_float(name, getattr(self, name))
        for name in ("daily_exposure", "market_exposure", "total_open_exposure"):
            _non_negative_float(name, getattr(self, name))
        if self.bankroll > self.peak_bankroll:
            raise ValueError("peak_bankroll cannot be below bankroll")


@dataclass(frozen=True)
class FootballWagerCandidate:
    fixture_id: str
    market_key: str
    selection_key: str
    model_version: str
    model_probability: float
    decimal_odds: float
    quoted_at: datetime
    evaluated_at: datetime
    phase: str
    evidence_sha256: str
    recovery_or_martingale_flag: bool = False

    def __post_init__(self) -> None:
        for name in ("fixture_id", "market_key", "selection_key", "model_version"):
            object.__setattr__(self, name, _required_text(name, getattr(self, name)))
        object.__setattr__(self, "model_probability", _probability("model_probability", self.model_probability))
        object.__setattr__(self, "decimal_odds", _positive_float("decimal_odds", self.decimal_odds))
        object.__setattr__(self, "quoted_at", _utc(self.quoted_at, name="quoted_at"))
        object.__setattr__(self, "evaluated_at", _utc(self.evaluated_at, name="evaluated_at"))
        if self.evaluated_at < self.quoted_at:
            raise ValueError("evaluated_at cannot be before quoted_at")
        phase = _required_text("phase", self.phase).upper()
        if phase not in {"PREMATCH", "LIVE"}:
            raise ValueError("phase must be PREMATCH or LIVE")
        object.__setattr__(self, "phase", phase)
        digest = _required_text("evidence_sha256", self.evidence_sha256).lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("evidence_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "evidence_sha256", digest)
        if not isinstance(self.recovery_or_martingale_flag, bool):
            raise TypeError("recovery_or_martingale_flag must be bool")


@dataclass(frozen=True)
class FootballHumanApproval:
    approval_id: str
    candidate_fingerprint: str
    approved_stake: float
    approved_at: datetime
    expires_at: datetime
    approver: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", _required_text("approval_id", self.approval_id))
        fingerprint = _required_text("candidate_fingerprint", self.candidate_fingerprint).lower()
        if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
            raise ValueError("candidate_fingerprint must be a SHA-256 hex digest")
        object.__setattr__(self, "candidate_fingerprint", fingerprint)
        object.__setattr__(self, "approved_stake", _positive_float("approved_stake", self.approved_stake))
        object.__setattr__(self, "approved_at", _utc(self.approved_at, name="approved_at"))
        object.__setattr__(self, "expires_at", _utc(self.expires_at, name="expires_at"))
        if self.expires_at <= self.approved_at:
            raise ValueError("expires_at must be after approved_at")
        object.__setattr__(self, "approver", _required_text("approver", self.approver))


@dataclass(frozen=True)
class FootballRiskGateInput:
    candidate: FootballWagerCandidate
    capital: FootballCapitalState
    controlled_live_review_eligible: bool
    odds_source_authorized: bool
    data_quality_passed: bool
    compliance_review_complete: bool
    kill_switch_manual_active: bool
    assessed_at: datetime
    approval: FootballHumanApproval | None = None
    consumed_approval_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessed_at", _utc(self.assessed_at, name="assessed_at"))
        if self.assessed_at < self.candidate.evaluated_at:
            raise ValueError("assessed_at cannot be before candidate.evaluated_at")
        if not isinstance(self.consumed_approval_ids, frozenset):
            raise TypeError("consumed_approval_ids must be frozenset")
        for approval_id in self.consumed_approval_ids:
            _required_text("consumed approval id", approval_id)


@dataclass(frozen=True)
class FootballRiskDecision:
    status: str
    review_allowed: bool
    approved_for_human_submission: bool
    automatic_wager_execution_enabled: bool
    full_kelly_fraction: float
    policy_kelly_fraction: float
    suggested_stake: float
    hard_stake_cap: float
    candidate_fingerprint: str
    blocked_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def candidate_fingerprint(candidate: FootballWagerCandidate, stake: float) -> str:
    stake_value = _positive_float("stake", stake)
    payload = "|".join(
        (
            candidate.fixture_id,
            candidate.market_key,
            candidate.selection_key,
            candidate.model_version,
            f"{candidate.model_probability:.12f}",
            f"{candidate.decimal_odds:.12f}",
            candidate.quoted_at.isoformat(),
            candidate.phase,
            candidate.evidence_sha256,
            f"{stake_value:.8f}",
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def full_kelly_fraction(probability: float, decimal_odds: float) -> float:
    p = _probability("probability", probability)
    odds = _positive_float("decimal_odds", decimal_odds)
    b = odds - 1.0
    if b <= 0:
        return 0.0
    fraction = (p * odds - 1.0) / b
    return max(0.0, fraction)


def _drawdown_fraction(current: float, reference: float) -> float:
    if current >= reference:
        return 0.0
    return (reference - current) / reference


def assess_football_real_money_risk(
    gate_input: FootballRiskGateInput,
    *,
    policy: FootballRiskPolicy = FootballRiskPolicy(),
) -> FootballRiskDecision:
    candidate = gate_input.candidate
    capital = gate_input.capital
    reasons: list[str] = []

    if not gate_input.controlled_live_review_eligible:
        reasons.append("controlled_live_evidence_gate_blocked")
    if not gate_input.odds_source_authorized:
        reasons.append("odds_source_not_authorized")
    if not gate_input.data_quality_passed:
        reasons.append("data_quality_gate_failed")
    if not gate_input.compliance_review_complete:
        reasons.append("compliance_review_incomplete")
    if gate_input.kill_switch_manual_active:
        reasons.append("manual_kill_switch_active")
    if candidate.recovery_or_martingale_flag:
        reasons.append("loss_recovery_or_martingale_forbidden")

    quote_age = (gate_input.assessed_at - candidate.quoted_at).total_seconds()
    max_age = (
        policy.max_live_quote_age_seconds
        if candidate.phase == "LIVE"
        else policy.max_prematch_quote_age_seconds
    )
    if quote_age > max_age:
        reasons.append("odds_quote_stale")
    if not policy.min_decimal_odds <= candidate.decimal_odds <= policy.max_decimal_odds:
        reasons.append("odds_outside_governed_range")

    daily_drawdown = _drawdown_fraction(capital.bankroll, capital.day_start_bankroll)
    peak_drawdown = _drawdown_fraction(capital.bankroll, capital.peak_bankroll)
    if daily_drawdown >= policy.daily_drawdown_kill_fraction:
        reasons.append("daily_drawdown_kill_switch")
    if peak_drawdown >= policy.peak_drawdown_kill_fraction:
        reasons.append("peak_drawdown_kill_switch")

    kelly = full_kelly_fraction(candidate.model_probability, candidate.decimal_odds)
    policy_kelly = min(kelly * policy.fractional_kelly, policy.max_stake_fraction_bankroll)
    hard_cap = capital.bankroll * policy.max_stake_fraction_bankroll
    suggested_stake = min(capital.bankroll * policy_kelly, hard_cap)

    if kelly <= 0:
        reasons.append("non_positive_model_edge")
    if suggested_stake <= 0:
        reasons.append("no_positive_stake")

    remaining_daily = capital.bankroll * policy.max_daily_exposure_fraction_bankroll - capital.daily_exposure
    remaining_market = capital.bankroll * policy.max_market_exposure_fraction_bankroll - capital.market_exposure
    remaining_total = capital.bankroll * policy.max_total_open_exposure_fraction_bankroll - capital.total_open_exposure
    exposure_cap = min(remaining_daily, remaining_market, remaining_total, hard_cap)
    if exposure_cap <= 0:
        reasons.append("exposure_limit_reached")
    else:
        suggested_stake = min(suggested_stake, exposure_cap)
        if suggested_stake <= 0:
            reasons.append("no_remaining_exposure_capacity")

    fingerprint_stake = suggested_stake if suggested_stake > 0 else max(hard_cap, 0.01)
    fingerprint = candidate_fingerprint(candidate, fingerprint_stake)

    approval = gate_input.approval
    if approval is None:
        reasons.append("human_approval_missing")
    else:
        if approval.approval_id in gate_input.consumed_approval_ids:
            reasons.append("human_approval_replay_detected")
        if approval.candidate_fingerprint != candidate_fingerprint(candidate, approval.approved_stake):
            reasons.append("human_approval_candidate_mismatch")
        if approval.approved_at < candidate.evaluated_at:
            reasons.append("human_approval_predates_candidate_evaluation")
        if approval.approved_at > gate_input.assessed_at:
            reasons.append("approval_from_future")
        if gate_input.assessed_at > approval.expires_at:
            reasons.append("human_approval_expired")
        if (approval.expires_at - approval.approved_at).total_seconds() > policy.approval_ttl_seconds:
            reasons.append("human_approval_ttl_exceeds_policy")
        if approval.approved_stake > hard_cap + 1e-9:
            reasons.append("human_approval_stake_above_hard_cap")
        if approval.approved_stake > max(exposure_cap, 0.0) + 1e-9:
            reasons.append("human_approval_stake_above_exposure_cap")
        if suggested_stake > 0 and approval.approved_stake > suggested_stake + 1e-9:
            reasons.append("human_approval_stake_above_model_risk_cap")
        fingerprint = approval.candidate_fingerprint

    blocked = tuple(dict.fromkeys(reasons))
    review_allowed = not any(
        reason
        for reason in blocked
        if reason not in {"human_approval_missing"}
    )
    approved = not blocked
    return FootballRiskDecision(
        status="HUMAN_SUBMISSION_APPROVED" if approved else "BLOCKED",
        review_allowed=review_allowed,
        approved_for_human_submission=approved,
        automatic_wager_execution_enabled=False,
        full_kelly_fraction=kelly,
        policy_kelly_fraction=policy_kelly,
        suggested_stake=round(max(0.0, suggested_stake), 2),
        hard_stake_cap=round(hard_cap, 2),
        candidate_fingerprint=fingerprint,
        blocked_reasons=blocked,
    )


def risk_policy_evidence_flags(decision: FootballRiskDecision) -> dict[str, bool]:
    return {
        "risk_policy_approved": decision.approved_for_human_submission,
        "kill_switch_verified": not any("kill_switch" in reason for reason in decision.blocked_reasons),
        "human_approval_required": True,
    }



@dataclass(frozen=True)
class FootballRiskControlAudit:
    passed: bool
    risk_policy_approved: bool
    kill_switch_verified: bool
    human_approval_required: bool
    automatic_wager_execution_enabled: bool
    blocked_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_football_risk_policy(
    policy: FootballRiskPolicy = FootballRiskPolicy(),
) -> FootballRiskControlAudit:
    reasons: list[str] = []
    if policy.fractional_kelly > 0.5:
        reasons.append("fractional_kelly_too_aggressive")
    if policy.max_stake_fraction_bankroll > 0.01:
        reasons.append("per_wager_cap_above_one_percent")
    if policy.max_daily_exposure_fraction_bankroll > 0.05:
        reasons.append("daily_exposure_cap_above_five_percent")
    if policy.max_total_open_exposure_fraction_bankroll > 0.05:
        reasons.append("open_exposure_cap_above_five_percent")
    if policy.daily_drawdown_kill_fraction > 0.05:
        reasons.append("daily_drawdown_kill_too_loose")
    if policy.peak_drawdown_kill_fraction > 0.15:
        reasons.append("peak_drawdown_kill_too_loose")
    if policy.max_live_quote_age_seconds > 10:
        reasons.append("live_quote_freshness_too_loose")
    if policy.approval_ttl_seconds > 60:
        reasons.append("human_approval_ttl_too_long")
    blocked = tuple(reasons)
    passed = not blocked
    return FootballRiskControlAudit(
        passed=passed,
        risk_policy_approved=passed,
        kill_switch_verified=passed,
        human_approval_required=True,
        automatic_wager_execution_enabled=False,
        blocked_reasons=blocked,
    )

def decision_from_mapping(payload: Mapping[str, Any]) -> FootballRiskDecision:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    return FootballRiskDecision(**dict(payload))
