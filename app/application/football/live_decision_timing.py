from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


LIVE_DECISION_STATES = (
    "DESCARTAR",
    "VIGILAR",
    "PRESENAL",
    "ENTRADA",
    "VENTANA_CERRADA",
)


def _aware(
    value: datetime | None,
    *,
    name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{name} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class LiveDecisionTiming:
    state: str
    source_observed_at: datetime | None
    captured_at: datetime
    evaluated_at: datetime
    signal_first_detected_at: datetime | None = None
    signal_confirmed_at: datetime | None = None
    market_entry_window_opened_at: datetime | None = None
    market_entry_window_closed_at: datetime | None = None
    missed_entry_reason: str | None = None
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.state not in LIVE_DECISION_STATES:
            raise ValueError(
                "INVALID_LIVE_DECISION_STATE"
            )

        names = (
            "source_observed_at",
            "captured_at",
            "evaluated_at",
            "signal_first_detected_at",
            "signal_confirmed_at",
            "market_entry_window_opened_at",
            "market_entry_window_closed_at",
        )
        for name in names:
            object.__setattr__(
                self,
                name,
                _aware(
                    getattr(self, name),
                    name=name,
                ),
            )

        if self.evaluated_at < self.captured_at:
            raise ValueError(
                "LIVE_EVALUATION_PRECEDES_CAPTURE"
            )
        if (
            self.source_observed_at is not None
            and self.captured_at
            < self.source_observed_at
        ):
            raise ValueError(
                "LIVE_CAPTURE_PRECEDES_SOURCE_OBSERVATION"
            )

        ordered = [
            value
            for value in (
                self.signal_first_detected_at,
                self.signal_confirmed_at,
                self.market_entry_window_opened_at,
                self.market_entry_window_closed_at,
            )
            if value is not None
        ]
        if any(
            right < left
            for left, right in zip(
                ordered,
                ordered[1:],
            )
        ):
            raise ValueError(
                "LIVE_SIGNAL_CHRONOLOGY_INVALID"
            )

        if self.automatic_wagering is not False:
            raise ValueError(
                "AUTOMATIC_WAGERING_FORBIDDEN"
            )

    @property
    def data_freshness_ms(self) -> int | None:
        if self.source_observed_at is None:
            return None
        return int(
            (
                self.captured_at
                - self.source_observed_at
            ).total_seconds()
            * 1000
        )

    @property
    def decision_latency_ms(self) -> int:
        return int(
            (
                self.evaluated_at
                - self.captured_at
            ).total_seconds()
            * 1000
        )

    @property
    def signal_confirmation_ms(self) -> int | None:
        if (
            self.signal_first_detected_at is None
            or self.signal_confirmed_at is None
        ):
            return None
        return int(
            (
                self.signal_confirmed_at
                - self.signal_first_detected_at
            ).total_seconds()
            * 1000
        )

    def payload(self) -> dict[str, object]:
        values = asdict(self)
        for key, value in tuple(
            values.items()
        ):
            if isinstance(value, datetime):
                values[key] = value.isoformat()
        values["data_freshness_ms"] = (
            self.data_freshness_ms
        )
        values["decision_latency_ms"] = (
            self.decision_latency_ms
        )
        values["signal_confirmation_ms"] = (
            self.signal_confirmation_ms
        )
        return values
