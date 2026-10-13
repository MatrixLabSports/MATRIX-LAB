from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CorrelationLimits:
    """Explicit governance limits. No defaults by design.

    The audit requires these limits to be decided by the team, not invented by
    the runtime.  Construction therefore requires all three values.
    """

    max_fixture_fraction: float
    max_tournament_day_fraction: float
    max_day_fraction: float

    def __post_init__(self) -> None:
        for name in (
            "max_fixture_fraction",
            "max_tournament_day_fraction",
            "max_day_fraction",
        ):
            value = float(getattr(self, name))
            if not 0 < value <= 1:
                raise ValueError(f"{name}_MUST_BE_IN_0_1")


@dataclass(frozen=True)
class ExposureRecord:
    fixture_id: str
    tournament_key: str
    operational_date: str
    stake: float

    def __post_init__(self) -> None:
        for name in ("fixture_id", "tournament_key", "operational_date"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name}_REQUIRED")
        if float(self.stake) <= 0:
            raise ValueError("STAKE_MUST_BE_POSITIVE")


@dataclass(frozen=True)
class CorrelatedExposureDecision:
    allowed: bool
    status: str
    fixture_exposure_after: float
    tournament_day_exposure_after: float
    day_exposure_after: float
    blocked_reasons: tuple[str, ...]
    mode: str = "PAPER_ONLY"
    real_money: str = "BLOCKED"


def assess_correlated_exposure(
    existing: Iterable[ExposureRecord],
    proposed: ExposureRecord,
    *,
    bankroll: float,
    limits: CorrelationLimits,
) -> CorrelatedExposureDecision:
    capital = float(bankroll)
    if capital <= 0:
        raise ValueError("BANKROLL_MUST_BE_POSITIVE")

    rows = list(existing)
    fixture = sum(
        float(x.stake)
        for x in rows
        if x.fixture_id == proposed.fixture_id
    ) + float(proposed.stake)
    tournament_day = sum(
        float(x.stake)
        for x in rows
        if x.tournament_key == proposed.tournament_key
        and x.operational_date == proposed.operational_date
    ) + float(proposed.stake)
    day = sum(
        float(x.stake)
        for x in rows
        if x.operational_date == proposed.operational_date
    ) + float(proposed.stake)

    reasons: list[str] = []
    if fixture > capital * limits.max_fixture_fraction + 1e-9:
        reasons.append("FIXTURE_CORRELATED_EXPOSURE_LIMIT")
    if tournament_day > capital * limits.max_tournament_day_fraction + 1e-9:
        reasons.append("TOURNAMENT_DAY_CORRELATED_EXPOSURE_LIMIT")
    if day > capital * limits.max_day_fraction + 1e-9:
        reasons.append("DAILY_AGGREGATE_EXPOSURE_LIMIT")

    return CorrelatedExposureDecision(
        allowed=not reasons,
        status="PASS_PAPER_EXPOSURE" if not reasons else "BLOCKED_CORRELATED_EXPOSURE",
        fixture_exposure_after=fixture,
        tournament_day_exposure_after=tournament_day,
        day_exposure_after=day,
        blocked_reasons=tuple(reasons),
    )
