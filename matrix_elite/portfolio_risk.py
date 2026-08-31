from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from random import Random
from typing import Sequence

from .risk import Position, exposure_audit


@dataclass(frozen=True)
class RiskBet:
    bet_id: str
    sport: str
    event_id: str
    market_id: str
    correlation_group: str
    stake_fraction: float
    win_probability: float
    decimal_odds: float

    def __post_init__(self) -> None:
        if not all(str(x).strip() for x in (self.bet_id, self.sport, self.event_id, self.market_id, self.correlation_group)):
            raise ValueError("RISK_BET_METADATA_REQUIRED")
        if self.stake_fraction <= 0 or self.stake_fraction >= 1:
            raise ValueError("RISK_STAKE_FRACTION_INVALID")
        if not 0 <= self.win_probability <= 1:
            raise ValueError("RISK_WIN_PROBABILITY_INVALID")
        if self.decimal_odds <= 1:
            raise ValueError("RISK_ODDS_INVALID")


@dataclass(frozen=True)
class PortfolioRiskPolicy:
    max_bet_fraction: float
    max_event_fraction: float
    max_day_fraction: float
    max_group_fraction: float
    max_group_latent_correlation: float
    max_probability_loss_20pct: float
    max_probability_loss_40pct: float
    max_actual_drawdown: float
    max_daily_realized_loss_fraction: float

    def __post_init__(self) -> None:
        fractions = (
            self.max_bet_fraction,
            self.max_event_fraction,
            self.max_day_fraction,
            self.max_group_fraction,
            self.max_probability_loss_20pct,
            self.max_probability_loss_40pct,
            self.max_actual_drawdown,
            self.max_daily_realized_loss_fraction,
        )
        if any(not 0 < x < 1 for x in fractions):
            raise ValueError("RISK_POLICY_FRACTION_INVALID")
        if not 0 <= self.max_group_latent_correlation < 1:
            raise ValueError("RISK_POLICY_CORRELATION_INVALID")


@dataclass(frozen=True)
class RuntimeRiskState:
    bankroll: float
    peak_bankroll: float
    daily_start_bankroll: float
    data_incident: bool = False
    model_incident: bool = False
    execution_incident: bool = False
    provider_incident: bool = False

    def __post_init__(self) -> None:
        if self.bankroll <= 0 or self.peak_bankroll <= 0 or self.daily_start_bankroll <= 0:
            raise ValueError("RUNTIME_BANKROLL_INVALID")
        if self.bankroll > self.peak_bankroll:
            raise ValueError("RUNTIME_PEAK_BANKROLL_INVALID")


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def monte_carlo_portfolio_stress(
    bets: Sequence[RiskBet],
    *,
    trials: int = 10000,
    group_latent_correlation: float = 0.25,
    seed: int = 836,
) -> dict[str, float | int]:
    if not bets:
        raise ValueError("RISK_BETS_REQUIRED")
    if trials < 1000:
        raise ValueError("RISK_TRIALS_TOO_SMALL")
    if not 0 <= group_latent_correlation < 1:
        raise ValueError("RISK_CORRELATION_INVALID")
    rng = Random(seed)
    group_names = sorted({b.correlation_group for b in bets})
    outcomes: list[float] = []
    rho = group_latent_correlation
    for _ in range(trials):
        group_z = {g: rng.gauss(0.0, 1.0) for g in group_names}
        pnl = 0.0
        for bet in bets:
            z = sqrt(rho) * group_z[bet.correlation_group] + sqrt(1.0 - rho) * rng.gauss(0.0, 1.0)
            u = _normal_cdf(z)
            win = u < bet.win_probability
            pnl += bet.stake_fraction * ((bet.decimal_odds - 1.0) if win else -1.0)
        outcomes.append(pnl)
    outcomes.sort()
    n = len(outcomes)
    def q(p: float) -> float:
        idx = min(n - 1, max(0, int((n - 1) * p)))
        return outcomes[idx]
    return {
        "trials": trials,
        "mean_pnl_fraction": sum(outcomes) / n,
        "p01_pnl_fraction": q(.01),
        "p05_pnl_fraction": q(.05),
        "median_pnl_fraction": q(.50),
        "probability_loss_20pct": sum(x <= -.20 for x in outcomes) / n,
        "probability_loss_40pct": sum(x <= -.40 for x in outcomes) / n,
        "worst_simulated_pnl_fraction": outcomes[0],
    }


def portfolio_risk_gate(
    bets: Sequence[RiskBet],
    *,
    policy: PortfolioRiskPolicy,
    trials: int = 10000,
    seed: int = 836,
) -> dict[str, object]:
    reasons: list[str] = []
    if any(b.stake_fraction > policy.max_bet_fraction for b in bets):
        reasons.append("BET_CAP_BREACH")
    exposure = exposure_audit(
        [Position(b.sport, b.event_id, b.market_id, b.stake_fraction, b.correlation_group) for b in bets],
        max_event=policy.max_event_fraction,
        max_day=policy.max_day_fraction,
        max_group=policy.max_group_fraction,
    )
    if exposure["event_cap_breached"]:
        reasons.append("EVENT_CAP_BREACH")
    if exposure["daily_cap_breached"]:
        reasons.append("DAY_CAP_BREACH")
    if exposure["correlation_cap_breached"]:
        reasons.append("GROUP_CAP_BREACH")
    stress = monte_carlo_portfolio_stress(
        bets,
        trials=trials,
        group_latent_correlation=policy.max_group_latent_correlation,
        seed=seed,
    )
    if stress["probability_loss_20pct"] > policy.max_probability_loss_20pct:
        reasons.append("TAIL_LOSS_20_PROBABILITY_BREACH")
    if stress["probability_loss_40pct"] > policy.max_probability_loss_40pct:
        reasons.append("TAIL_LOSS_40_PROBABILITY_BREACH")
    return {"pass": not reasons, "reasons": tuple(reasons), "exposure": exposure, "stress": stress}


def runtime_kill_switch(state: RuntimeRiskState, *, policy: PortfolioRiskPolicy) -> dict[str, object]:
    reasons: list[str] = []
    drawdown = (state.peak_bankroll - state.bankroll) / state.peak_bankroll
    daily_loss = max(0.0, (state.daily_start_bankroll - state.bankroll) / state.daily_start_bankroll)
    if drawdown >= policy.max_actual_drawdown:
        reasons.append("MAX_DRAWDOWN_KILL")
    if daily_loss >= policy.max_daily_realized_loss_fraction:
        reasons.append("DAILY_LOSS_KILL")
    if state.data_incident:
        reasons.append("DATA_INCIDENT_KILL")
    if state.model_incident:
        reasons.append("MODEL_INCIDENT_KILL")
    if state.execution_incident:
        reasons.append("EXECUTION_INCIDENT_KILL")
    if state.provider_incident:
        reasons.append("PROVIDER_INCIDENT_KILL")
    return {"kill": bool(reasons), "reasons": tuple(reasons), "drawdown": drawdown, "daily_loss": daily_loss}
