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


def _paper_exposure_rows(
    ledger: dict,
    *,
    provisional: Iterable[dict] = (),
) -> list[dict]:
    rows: list[dict] = []
    for record in ledger.get("sent", []):
        if not isinstance(record, dict):
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        status = str(bet.get("status") or "").upper()
        if status in {"CANCELLED_NO_BET", "VOID_POSTPONED"} or status.startswith("EXCLUDED"):
            continue
        stake = float(bet.get("stake_cop") or 0.0)
        day = str(bet.get("kickoff_bogota_date") or "").strip()
        fixture_id = str(record.get("fixture_id") or "").strip()
        tournament_key = str(record.get("league_id") or "").strip()
        if stake <= 0 or not day or not fixture_id or not tournament_key:
            continue
        rows.append({
            "fixture_id": fixture_id,
            "tournament_key": tournament_key,
            "operational_date": day,
            "stake_cop": stake,
        })
    for row in provisional:
        if not isinstance(row, dict):
            continue
        stake = float(row.get("stake_cop") or 0.0)
        fixture_id = str(row.get("fixture_id") or "").strip()
        tournament_key = str(row.get("tournament_key") or "").strip()
        day = str(row.get("operational_date") or "").strip()
        if stake > 0 and fixture_id and tournament_key and day:
            rows.append({
                "fixture_id": fixture_id,
                "tournament_key": tournament_key,
                "operational_date": day,
                "stake_cop": stake,
            })
    return rows


def _group_max(rows: list[dict], key_fields: tuple[str, ...]) -> float:
    grouped: dict[tuple[str, ...], float] = {}
    for row in rows:
        key = tuple(str(row[field]) for field in key_fields)
        grouped[key] = grouped.get(key, 0.0) + float(row["stake_cop"])
    return max(grouped.values(), default=0.0)


def calibrate_paper_correlated_exposure(
    ledger: dict,
    *,
    initial_bankroll_cop: float,
    unit_cop: float,
    max_signals_per_tournament_day: int,
    daily_policy_cap_fraction: float,
) -> dict:
    """Calibrate conservative concentration caps from the physical paper ledger.

    No synthetic correlation coefficient is invented.  The current Telegram
    ledger is a single-market Over 2.5 history, so pairwise cross-market
    correlation remains unidentifiable and H-02 must stay open.  Runtime caps
    therefore use empirical observed concentration bounded by existing
    governance: one unit per fixture, the existing signals-per-league/day cap,
    and the existing daily exposure ceiling.
    """
    capital = float(initial_bankroll_cop)
    unit = float(unit_cop)
    league_count_cap = int(max_signals_per_tournament_day)
    daily_ceiling = float(daily_policy_cap_fraction)
    if capital <= 0 or unit <= 0 or league_count_cap <= 0 or not 0 < daily_ceiling <= 1:
        raise ValueError("CORRELATED_RISK_CALIBRATION_INPUT_INVALID")

    rows = _paper_exposure_rows(ledger)
    observed_fixture = _group_max(rows, ("operational_date", "fixture_id"))
    observed_tournament_day = _group_max(rows, ("operational_date", "tournament_key"))
    observed_day = _group_max(rows, ("operational_date",))

    fixture_cap_cop = unit
    tournament_day_policy_cap_cop = unit * league_count_cap
    tournament_day_cap_cop = min(
        max(unit, observed_tournament_day or unit),
        tournament_day_policy_cap_cop,
    )
    observed_day_fraction = observed_day / capital if observed_day > 0 else 0.0
    daily_cap_fraction = min(
        max(unit / capital, observed_day_fraction or (unit / capital)),
        daily_ceiling,
    )

    return {
        "schema": "MATRIX_EMPIRICAL_CORRELATED_EXPOSURE_CALIBRATION_V1",
        "status": "READY_FAIL_CLOSED" if rows else "INSUFFICIENT_LEDGER_FAIL_CLOSED",
        "sample_records": len(rows),
        "basis": "PHYSICAL_PAPER_LEDGER_NO_SYNTHETIC_CORRELATION",
        "observed_maxima_cop": {
            "same_fixture_day": observed_fixture,
            "same_tournament_day": observed_tournament_day,
            "operational_day": observed_day,
        },
        "caps": {
            "fixture_cap_cop": fixture_cap_cop,
            "tournament_day_cap_cop": tournament_day_cap_cop,
            "tournament_day_policy_ceiling_cop": tournament_day_policy_cap_cop,
            "daily_cap_fraction": daily_cap_fraction,
            "daily_policy_ceiling_fraction": daily_ceiling,
        },
        "pairwise_cross_market_correlation": {
            "calibrated": False,
            "reason": "SINGLE_MARKET_TELEGRAM_LEDGER_NO_ADJUDICABLE_CROSS_MARKET_PAIRS",
        },
        "h02_closed": False,
        "real_money": "BLOCKED",
    }


def assess_paper_correlated_exposure(
    ledger: dict,
    proposed: dict,
    *,
    calibration: dict,
    bankroll_cop: float,
    provisional: Iterable[dict] = (),
) -> dict:
    if calibration.get("status") != "READY_FAIL_CLOSED":
        return {
            "allowed": False,
            "status": "BLOCKED_CORRELATED_RISK_CALIBRATION_NOT_READY",
            "blocked_reasons": ["CORRELATED_RISK_CALIBRATION_NOT_READY"],
            "real_money": "BLOCKED",
        }

    fixture_id = str(proposed.get("fixture_id") or "").strip()
    tournament_key = str(proposed.get("tournament_key") or "").strip()
    day = str(proposed.get("operational_date") or "").strip()
    stake = float(proposed.get("stake_cop") or 0.0)
    if not fixture_id or not tournament_key or not day or stake <= 0:
        return {
            "allowed": False,
            "status": "BLOCKED_CORRELATED_RISK_METADATA_MISSING",
            "blocked_reasons": ["CORRELATED_RISK_METADATA_MISSING"],
            "real_money": "BLOCKED",
        }

    rows = _paper_exposure_rows(ledger, provisional=provisional)
    fixture_before = sum(
        float(x["stake_cop"]) for x in rows
        if x["operational_date"] == day and x["fixture_id"] == fixture_id
    )
    tournament_before = sum(
        float(x["stake_cop"]) for x in rows
        if x["operational_date"] == day and x["tournament_key"] == tournament_key
    )
    day_before = sum(
        float(x["stake_cop"]) for x in rows
        if x["operational_date"] == day
    )

    caps = calibration["caps"]
    fixture_after = fixture_before + stake
    tournament_after = tournament_before + stake
    day_after = day_before + stake
    day_cap_cop = float(bankroll_cop) * float(caps["daily_cap_fraction"])

    reasons: list[str] = []
    if fixture_after > float(caps["fixture_cap_cop"]) + 1e-9:
        reasons.append("FIXTURE_CORRELATED_EXPOSURE_LIMIT")
    if tournament_after > float(caps["tournament_day_cap_cop"]) + 1e-9:
        reasons.append("TOURNAMENT_DAY_CORRELATED_EXPOSURE_LIMIT")
    if day_after > day_cap_cop + 1e-9:
        reasons.append("DAILY_AGGREGATE_EXPOSURE_LIMIT")

    return {
        "allowed": not reasons,
        "status": "PASS_PAPER_CORRELATED_RISK_GATE" if not reasons else "BLOCKED_CORRELATED_EXPOSURE",
        "blocked_reasons": reasons,
        "fixture_exposure_after_cop": fixture_after,
        "tournament_day_exposure_after_cop": tournament_after,
        "day_exposure_after_cop": day_after,
        "fixture_cap_cop": float(caps["fixture_cap_cop"]),
        "tournament_day_cap_cop": float(caps["tournament_day_cap_cop"]),
        "day_cap_cop": day_cap_cop,
        "mode": "PAPER_ONLY",
        "h02_closed": False,
        "real_money": "BLOCKED",
    }
