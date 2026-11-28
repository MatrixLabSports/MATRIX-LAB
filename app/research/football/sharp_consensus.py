from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping


SHARP_REFERENCE_SOURCES = ("pinnacle", "circa", "betfair")
MARKET_CONTEXT_SOURCES = ("fanduel",)
DEFAULT_MAX_ABS_GAP = 0.07


@dataclass(frozen=True)
class SharpQuote:
    source: str
    over_odds: float
    under_odds: float
    quote_age_seconds: int | None = None
    market: str = "over_2_5"

    def no_vig_over_probability(self) -> float:
        if self.over_odds <= 1.0 or self.under_odds <= 1.0:
            raise ValueError("INVALID_DECIMAL_ODDS")
        over = 1.0 / self.over_odds
        under = 1.0 / self.under_odds
        denom = over + under
        if denom <= 0:
            raise ValueError("INVALID_OVERROUND")
        return over / denom


def _norm_source(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "")


def assess_sharp_consensus(
    *,
    p_matrix: float,
    quotes: Iterable[SharpQuote | Mapping[str, Any]],
    max_quote_age_seconds: int = 120,
    max_abs_gap: float = DEFAULT_MAX_ABS_GAP,
) -> dict[str, Any]:
    if not 0.0 < float(p_matrix) < 1.0:
        raise ValueError("P_MATRIX_OUT_OF_RANGE")

    sharp_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in quotes:
        quote = raw if isinstance(raw, SharpQuote) else SharpQuote(
            source=str(raw.get("source") or ""),
            over_odds=float(raw["over_odds"]),
            under_odds=float(raw["under_odds"]),
            quote_age_seconds=None if raw.get("quote_age_seconds") is None else int(raw["quote_age_seconds"]),
            market=str(raw.get("market") or "over_2_5"),
        )
        source = _norm_source(quote.source)
        if quote.market != "over_2_5":
            rejected.append({"source": source, "reason": "MARKET_MISMATCH"})
            continue
        if quote.quote_age_seconds is not None and quote.quote_age_seconds > max_quote_age_seconds:
            rejected.append({"source": source, "reason": "STALE_QUOTE", "quote_age_seconds": quote.quote_age_seconds})
            continue
        try:
            fair_p = quote.no_vig_over_probability()
        except ValueError as exc:
            rejected.append({"source": source, "reason": str(exc)})
            continue

        row = {
            "source": source,
            "no_vig_over_probability": round(fair_p, 10),
            "over_odds": quote.over_odds,
            "under_odds": quote.under_odds,
            "quote_age_seconds": quote.quote_age_seconds,
        }
        if source in SHARP_REFERENCE_SOURCES:
            sharp_rows.append(row)
        elif source in MARKET_CONTEXT_SOURCES:
            context_rows.append(row)
        else:
            rejected.append({"source": source, "reason": "UNAPPROVED_REFERENCE_SOURCE"})

    unique_sharp: dict[str, dict[str, Any]] = {}
    for row in sharp_rows:
        unique_sharp[row["source"]] = row
    sharp_rows = [unique_sharp[k] for k in SHARP_REFERENCE_SOURCES if k in unique_sharp]

    consensus_probability = None
    gap = None
    if sharp_rows:
        consensus_probability = float(median([float(x["no_vig_over_probability"]) for x in sharp_rows]))
        gap = float(p_matrix) - consensus_probability

    coverage = len(sharp_rows)
    if coverage >= 2 and gap is not None:
        status = "PASS_ALIGNED" if abs(gap) < max_abs_gap else "CONTRADICTION_REVIEW"
    elif coverage == 1:
        status = "SINGLE_SHARP_REFERENCE_ONLY"
    else:
        status = "INSUFFICIENT_SHARP_COVERAGE"

    return {
        "schema": "MATRIX_FOOTBALL_SHARP_CONSENSUS_GATE_V1",
        "market": "OVER_2_5",
        "p_matrix": round(float(p_matrix), 10),
        "sharp_reference_policy": {
            "consensus_sources": list(SHARP_REFERENCE_SOURCES),
            "market_context_only": list(MARKET_CONTEXT_SOURCES),
            "max_quote_age_seconds": int(max_quote_age_seconds),
            "contradiction_abs_gap_threshold": float(max_abs_gap),
            "p_matrix_mutated_by_odds": False,
            "probability_source": "MODEL_ONLY",
        },
        "sharp_rows": sharp_rows,
        "market_context_rows": context_rows,
        "rejected_rows": rejected,
        "sharp_source_count": coverage,
        "sharp_consensus_probability": None if consensus_probability is None else round(consensus_probability, 10),
        "p_matrix_minus_sharp_consensus": None if gap is None else round(gap, 10),
        "status": status,
        "signal_action": "REVIEW_ONLY",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
