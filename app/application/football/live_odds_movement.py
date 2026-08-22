from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable


def _aware(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _odds(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("INVALID_DECIMAL_ODDS")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("INVALID_DECIMAL_ODDS") from error
    if parsed <= 1.0:
        raise ValueError("INVALID_DECIMAL_ODDS")
    return parsed


@dataclass(frozen=True)
class LiveOddsObservation:
    provider: str
    bookmaker: str
    fixture_id: str
    market_key: str
    selection_key: str
    captured_at: datetime
    decimal_odds: float

    def __post_init__(self) -> None:
        for name in (
            "provider",
            "bookmaker",
            "fixture_id",
            "market_key",
            "selection_key",
        ):
            if not str(
                getattr(self, name)
            ).strip():
                raise ValueError(
                    f"{name.upper()}_REQUIRED"
                )
        object.__setattr__(
            self,
            "captured_at",
            _aware(
                self.captured_at,
                name="captured_at",
            ),
        )
        object.__setattr__(
            self,
            "decimal_odds",
            _odds(self.decimal_odds),
        )


@dataclass(frozen=True)
class LiveOddsMovement:
    provider: str
    bookmaker: str
    fixture_id: str
    market_key: str
    selection_key: str
    previous_odds: float
    current_odds: float
    change_pct: float
    velocity_pct_per_minute: float
    implied_probability_delta: float
    direction: str
    elapsed_seconds: float

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CrossBookMovementSummary:
    market_key: str
    selection_key: str
    movement_count: int
    steam_count: int
    drift_count: int
    unchanged_count: int
    direction: str

    def payload(self) -> dict[str, object]:
        return asdict(self)


def calculate_live_odds_movement(
    previous: LiveOddsObservation,
    current: LiveOddsObservation,
) -> LiveOddsMovement:
    identity = (
        "provider",
        "bookmaker",
        "fixture_id",
        "market_key",
        "selection_key",
    )
    if any(
        getattr(previous, name)
        != getattr(current, name)
        for name in identity
    ):
        raise ValueError(
            "LIVE_ODDS_IDENTITY_MISMATCH"
        )

    elapsed = (
        current.captured_at
        - previous.captured_at
    ).total_seconds()
    if elapsed <= 0:
        raise ValueError(
            "LIVE_ODDS_CHRONOLOGY_INVALID"
        )

    change_pct = (
        (
            previous.decimal_odds
            - current.decimal_odds
        )
        / previous.decimal_odds
        * 100.0
    )
    velocity = change_pct / (
        elapsed / 60.0
    )
    implied_delta = (
        1.0 / current.decimal_odds
        - 1.0 / previous.decimal_odds
    )

    if current.decimal_odds < previous.decimal_odds:
        direction = "STEAM"
    elif current.decimal_odds > previous.decimal_odds:
        direction = "DRIFT"
    else:
        direction = "UNCHANGED"

    return LiveOddsMovement(
        provider=current.provider,
        bookmaker=current.bookmaker,
        fixture_id=current.fixture_id,
        market_key=current.market_key,
        selection_key=current.selection_key,
        previous_odds=previous.decimal_odds,
        current_odds=current.decimal_odds,
        change_pct=change_pct,
        velocity_pct_per_minute=velocity,
        implied_probability_delta=implied_delta,
        direction=direction,
        elapsed_seconds=elapsed,
    )


def summarize_cross_book_movements(
    movements: Iterable[LiveOddsMovement],
) -> CrossBookMovementSummary:
    rows = tuple(movements)
    if not rows:
        raise ValueError(
            "CROSS_BOOK_MOVEMENTS_REQUIRED"
        )

    market = rows[0].market_key
    selection = rows[0].selection_key
    if any(
        row.market_key != market
        or row.selection_key != selection
        for row in rows
    ):
        raise ValueError(
            "CROSS_BOOK_MARKET_MISMATCH"
        )

    books = {
        (row.provider, row.bookmaker)
        for row in rows
    }
    if len(books) != len(rows):
        raise ValueError(
            "DUPLICATE_CROSS_BOOK_SOURCE"
        )

    steam = sum(
        row.direction == "STEAM"
        for row in rows
    )
    drift = sum(
        row.direction == "DRIFT"
        for row in rows
    )
    unchanged = sum(
        row.direction == "UNCHANGED"
        for row in rows
    )

    if len(rows) < 2:
        direction = "INSUFFICIENT_CROSS_BOOK_EVIDENCE"
    elif steam == len(rows):
        direction = "STEAM"
    elif drift == len(rows):
        direction = "DRIFT"
    elif unchanged == len(rows):
        direction = "UNCHANGED"
    else:
        direction = "MIXED"

    return CrossBookMovementSummary(
        market_key=market,
        selection_key=selection,
        movement_count=len(rows),
        steam_count=steam,
        drift_count=drift,
        unchanged_count=unchanged,
        direction=direction,
    )
