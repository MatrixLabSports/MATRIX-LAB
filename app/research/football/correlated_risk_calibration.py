from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil, sqrt
from statistics import mean
from typing import Any


CANCELLED_STATUSES = {"CANCELLED_NO_BET", "VOID_POSTPONED"}
DEFAULT_UNIT_FRACTION = 0.005
EXISTING_LEAGUE_DAY_SIGNAL_CAP = 3
EXISTING_DAILY_GOVERNANCE_CAP = 0.30


@dataclass(frozen=True)
class EmpiricalCorrelationCalibration:
    status: str
    sample_settled: int
    pair_count_same_league_day: int
    observed_pair_agreement_rate: float | None
    agreement_wilson_upper95: float | None
    fixture_cap_fraction: float
    tournament_day_cap_fraction: float
    day_cap_fraction: float
    source: str = "TELEGRAM_PAPER_LEDGER_REAL_SETTLED_ONLY"
    real_money: str = "BLOCKED"


def _wilson_upper(successes: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = successes / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    radius = z * sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return min(1.0, (centre + radius) / den)


def _nearest_rank(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    rows = sorted(float(x) for x in values)
    idx = max(0, min(len(rows) - 1, ceil(q * len(rows)) - 1))
    return rows[idx]


def _paper_rows(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    settlements = {
        str(x.get("signal_key") or ""): x
        for x in ledger.get("settlements", [])
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    out: list[dict[str, Any]] = []
    for record in ledger.get("sent", []):
        if not isinstance(record, dict):
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        status = str(bet.get("status") or "").upper()
        if status in CANCELLED_STATUSES or status != "SETTLED":
            continue
        stake = float(bet.get("stake_cop") or 0.0)
        bankroll = float(bet.get("bankroll_before_cop") or 0.0)
        if stake <= 0 or bankroll <= 0:
            continue
        signal_key = str(record.get("signal_key") or "")
        settlement = settlements.get(signal_key, {})
        won = settlement.get("won")
        if not isinstance(won, bool):
            continue
        day = str(
            bet.get("kickoff_bogota_date")
            or str(record.get("kickoff") or "")[:10]
        ).strip()
        fixture = str(record.get("fixture_id") or "").strip()
        league = str(record.get("league_id") or "").strip()
        if not day or not fixture:
            continue
        out.append({
            "signal_key": signal_key,
            "fixture_id": fixture,
            "league_id": league or "UNKNOWN",
            "day": day,
            "stake_fraction": stake / bankroll,
            "won": won,
        })
    return out


def calibrate_correlated_risk_from_ledger(ledger: dict[str, Any]) -> EmpiricalCorrelationCalibration:
    rows = _paper_rows(ledger)
    if len(rows) < 30:
        return EmpiricalCorrelationCalibration(
            status="BLOCKED_INSUFFICIENT_REAL_SETTLED_SAMPLE",
            sample_settled=len(rows),
            pair_count_same_league_day=0,
            observed_pair_agreement_rate=None,
            agreement_wilson_upper95=None,
            fixture_cap_fraction=DEFAULT_UNIT_FRACTION,
            tournament_day_cap_fraction=DEFAULT_UNIT_FRACTION,
            day_cap_fraction=DEFAULT_UNIT_FRACTION,
        )

    fixture = defaultdict(float)
    league_day = defaultdict(float)
    day = defaultdict(float)
    outcomes = defaultdict(list)
    for row in rows:
        f = float(row["stake_fraction"])
        fixture[(row["day"], row["fixture_id"])] += f
        league_day[(row["day"], row["league_id"])] += f
        day[row["day"]] += f
        outcomes[(row["day"], row["league_id"])].append(bool(row["won"]))

    pair_total = 0
    pair_agree = 0
    for vals in outcomes.values():
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                pair_total += 1
                pair_agree += int(vals[i] == vals[j])

    agreement = (pair_agree / pair_total) if pair_total else None
    upper = _wilson_upper(pair_agree, pair_total) if pair_total else None

    # Empirical concentration caps use the real 95th percentile but may never
    # exceed the already-governed 1u-per-fixture, 3-signals-per-league-day,
    # and 30%-per-day ceilings. This avoids legitimising historical overexposure.
    unit = DEFAULT_UNIT_FRACTION
    fixture_cap = min(max(unit, _nearest_rank(list(fixture.values()), 0.95)), unit)
    league_governance_ceiling = EXISTING_LEAGUE_DAY_SIGNAL_CAP * unit
    league_cap = min(
        max(unit, _nearest_rank(list(league_day.values()), 0.95)),
        league_governance_ceiling,
    )
    daily_cap = min(
        max(unit, _nearest_rank(list(day.values()), 0.95)),
        EXISTING_DAILY_GOVERNANCE_CAP,
    )

    return EmpiricalCorrelationCalibration(
        status="PASS_EMPIRICAL_CONCENTRATION_CALIBRATION",
        sample_settled=len(rows),
        pair_count_same_league_day=pair_total,
        observed_pair_agreement_rate=agreement,
        agreement_wilson_upper95=upper,
        fixture_cap_fraction=fixture_cap,
        tournament_day_cap_fraction=league_cap,
        day_cap_fraction=daily_cap,
    )


def calibration_evidence(cal: EmpiricalCorrelationCalibration) -> dict[str, Any]:
    return {
        "schema": "MATRIX_CORRELATED_RISK_CALIBRATION_V1",
        "status": cal.status,
        "sample_settled": cal.sample_settled,
        "same_league_day_outcome_pairs": cal.pair_count_same_league_day,
        "observed_pair_agreement_rate": cal.observed_pair_agreement_rate,
        "agreement_wilson_upper95": cal.agreement_wilson_upper95,
        "limits": {
            "max_fixture_fraction": cal.fixture_cap_fraction,
            "max_tournament_day_fraction": cal.tournament_day_cap_fraction,
            "max_day_fraction": cal.day_cap_fraction,
        },
        "method": {
            "sample": "real settled paper bets only",
            "concentration_quantile": "nearest-rank p95",
            "fixture_ceiling": "1u = 0.5% initial bankroll",
            "tournament_day_ceiling": "existing 3-signal league/day policy = 1.5% under flat 1u",
            "day_ceiling": "existing governed daily cap = 30%",
            "pair_dependence_diagnostic": "same-league/day binary outcome agreement + Wilson 95% upper bound",
            "historical_overexposure_can_raise_caps": False,
        },
        "protections": {
            "p_matrix_modified": False,
            "ev_modified": False,
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
