from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any, Mapping, Sequence


UTC = timezone.utc


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _aware(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _finite(
    name: str,
    value: object,
    *,
    minimum: float | None = None,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(f"INVALID_{name}")

    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"INVALID_{name}")

    if minimum is not None and number < minimum:
        raise ValueError(f"INVALID_{name}")

    return number


def _count(name: str, value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ValueError(f"INVALID_{name}")
    return value


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class SportLoadContext:
    sport: str
    canonical_id: str
    as_of: datetime
    event_at: datetime
    available_at: datetime
    previous_event_end_at: datetime | None
    rest_hours: float | None
    travel_km: float | None
    timezone_shift_hours: float | None
    altitude_delta_m: float | None
    matches_last_7d: int
    matches_last_14d: int
    cumulative_minutes_last_7d: float | None
    cumulative_minutes_last_14d: float | None
    source_record_fingerprints: tuple[str, ...]
    context_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                f"matrix.{self.sport}-load-context/2"
            ),
            "sport": self.sport,
            "canonical_id": self.canonical_id,
            "as_of": (
                self.as_of
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "event_at": (
                self.event_at
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "available_at": (
                self.available_at
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "previous_event_end_at": (
                None
                if self.previous_event_end_at is None
                else (
                    self.previous_event_end_at
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            ),
            "rest_hours": self.rest_hours,
            "travel_km": self.travel_km,
            "timezone_shift_hours": (
                self.timezone_shift_hours
            ),
            "altitude_delta_m": (
                self.altitude_delta_m
            ),
            "matches_last_7d": (
                self.matches_last_7d
            ),
            "matches_last_14d": (
                self.matches_last_14d
            ),
            "cumulative_minutes_last_7d": (
                self.cumulative_minutes_last_7d
            ),
            "cumulative_minutes_last_14d": (
                self.cumulative_minutes_last_14d
            ),
            "source_record_fingerprints": list(
                self.source_record_fingerprints
            ),
            "context_fingerprint": (
                self.context_fingerprint
            ),
            "fatigue_score_computed": False,
            "point_in_time_enforced": True,
            "missing_is_zero": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }


def build_sport_load_context(
    *,
    sport: str,
    canonical_id: str,
    as_of: datetime,
    event_at: datetime,
    available_at: datetime,
    previous_event_end_at: datetime | None,
    travel_km: float | None,
    timezone_shift_hours: float | None,
    altitude_delta_m: float | None,
    matches_last_7d: int,
    matches_last_14d: int,
    cumulative_minutes_last_7d: float | None,
    cumulative_minutes_last_14d: float | None,
    source_record_fingerprints: Sequence[str],
) -> SportLoadContext:
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")

    if (
        not isinstance(canonical_id, str)
        or not canonical_id
    ):
        raise ValueError("INVALID_CANONICAL_ID")

    as_of = _aware("AS_OF", as_of)
    event_at = _aware("EVENT_AT", event_at)
    available_at = _aware(
        "AVAILABLE_AT",
        available_at,
    )

    if available_at > as_of:
        raise ValueError(
            "CONTEXT_NOT_AVAILABLE_AS_OF"
        )

    if event_at < as_of:
        raise ValueError(
            "TARGET_EVENT_BEFORE_AS_OF"
        )

    previous_end = None

    if previous_event_end_at is None:
        rest_hours = None
    else:
        previous_end = _aware(
            "PREVIOUS_EVENT_END_AT",
            previous_event_end_at,
        )

        if previous_end >= event_at:
            raise ValueError(
                "INVALID_PREVIOUS_EVENT_END_AT"
            )

        rest_hours = (
            event_at - previous_end
        ).total_seconds() / 3600.0

    travel = (
        None
        if travel_km is None
        else _finite(
            "TRAVEL_KM",
            travel_km,
            minimum=0,
        )
    )

    tz_shift = (
        None
        if timezone_shift_hours is None
        else _finite(
            "TIMEZONE_SHIFT_HOURS",
            timezone_shift_hours,
        )
    )

    altitude = (
        None
        if altitude_delta_m is None
        else _finite(
            "ALTITUDE_DELTA_M",
            altitude_delta_m,
        )
    )

    matches7 = _count(
        "MATCHES_LAST_7D",
        matches_last_7d,
    )
    matches14 = _count(
        "MATCHES_LAST_14D",
        matches_last_14d,
    )

    if matches7 > matches14:
        raise ValueError(
            "MATCH_COUNT_WINDOW_INCONSISTENCY"
        )

    minutes7 = (
        None
        if cumulative_minutes_last_7d is None
        else _finite(
            "CUMULATIVE_MINUTES_LAST_7D",
            cumulative_minutes_last_7d,
            minimum=0,
        )
    )

    minutes14 = (
        None
        if cumulative_minutes_last_14d is None
        else _finite(
            "CUMULATIVE_MINUTES_LAST_14D",
            cumulative_minutes_last_14d,
            minimum=0,
        )
    )

    if (
        minutes7 is not None
        and minutes14 is not None
        and minutes7 > minutes14
    ):
        raise ValueError(
            "MINUTES_WINDOW_INCONSISTENCY"
        )

    if (
        isinstance(
            source_record_fingerprints,
            (str, bytes),
        )
        or not isinstance(
            source_record_fingerprints,
            Sequence,
        )
        or not source_record_fingerprints
    ):
        raise ValueError(
            "EMPTY_CONTEXT_SOURCE_RECORDS"
        )

    source_fps = tuple(
        sorted(
            {
                _hex64(
                    "SOURCE_RECORD_FINGERPRINT",
                    value,
                )
                for value
                in source_record_fingerprints
            }
        )
    )

    base = {
        "schema": (
            f"matrix.{sport}-load-context/2"
        ),
        "sport": sport,
        "canonical_id": canonical_id,
        "as_of": (
            as_of
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "event_at": (
            event_at
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "available_at": (
            available_at
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "previous_event_end_at": (
            None
            if previous_end is None
            else (
                previous_end
                .isoformat()
                .replace("+00:00", "Z")
            )
        ),
        "rest_hours": rest_hours,
        "travel_km": travel,
        "timezone_shift_hours": tz_shift,
        "altitude_delta_m": altitude,
        "matches_last_7d": matches7,
        "matches_last_14d": matches14,
        "cumulative_minutes_last_7d": minutes7,
        "cumulative_minutes_last_14d": minutes14,
        "source_record_fingerprints": list(
            source_fps
        ),
        "fatigue_score_computed": False,
        "point_in_time_enforced": True,
        "missing_is_zero": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return SportLoadContext(
        sport=sport,
        canonical_id=canonical_id,
        as_of=as_of,
        event_at=event_at,
        available_at=available_at,
        previous_event_end_at=previous_end,
        rest_hours=rest_hours,
        travel_km=travel,
        timezone_shift_hours=tz_shift,
        altitude_delta_m=altitude,
        matches_last_7d=matches7,
        matches_last_14d=matches14,
        cumulative_minutes_last_7d=minutes7,
        cumulative_minutes_last_14d=minutes14,
        source_record_fingerprints=source_fps,
        context_fingerprint=_sha(base),
    )
