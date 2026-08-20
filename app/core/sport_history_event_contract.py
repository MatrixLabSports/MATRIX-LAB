from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any, Mapping


UTC = timezone.utc

_ALLOWED_TENNIS_SURFACES = {
    "hard",
    "clay",
    "grass",
    "carpet",
    "unknown",
}
_ALLOWED_TENNIS_OUTCOMES = {"W", "L", "UNKNOWN"}
_ALLOWED_FOOTBALL_OUTCOMES = {"W", "D", "L", "UNKNOWN"}
_ALLOWED_FOOTBALL_VENUES = {
    "home",
    "away",
    "neutral",
    "unknown",
}


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


def _parse_aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_{name}")

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")

    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip()


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


def _validate_metrics(
    value: object,
) -> Mapping[str, float | int | None]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_HISTORY_METRICS")

    normalized: dict[str, float | int | None] = {}

    for raw_key, raw_value in value.items():
        key = _nonempty("METRIC_KEY", raw_key)

        if raw_value is None:
            normalized[key] = None
            continue

        if isinstance(raw_value, bool) or not isinstance(
            raw_value,
            (int, float),
        ):
            raise ValueError(
                f"INVALID_HISTORY_METRIC_VALUE:{key}"
            )

        if not math.isfinite(float(raw_value)):
            raise ValueError(
                f"NONFINITE_HISTORY_METRIC_VALUE:{key}"
            )

        normalized[key] = raw_value

    return dict(sorted(normalized.items()))


@dataclass(frozen=True)
class TennisHistoryEvent:
    event_key: str
    event_at: datetime
    season_key: str
    competition_key: str
    opponent_canonical_id: str
    outcome: str
    completed: bool
    retirement: bool
    surface: str
    indoor: bool | None
    metrics: Mapping[str, float | int | None]
    source_record_fingerprint: str
    source_available_at: datetime
    event_fingerprint: str


@dataclass(frozen=True)
class FootballHistoryEvent:
    event_key: str
    event_at: datetime
    season_key: str
    competition_key: str
    opponent_canonical_id: str
    outcome: str
    completed: bool
    venue: str
    metrics: Mapping[str, float | int | None]
    source_record_fingerprint: str
    source_available_at: datetime
    event_fingerprint: str


def _observation_common(
    observation: Mapping[str, Any],
    *,
    expected_sport: str,
) -> tuple[
    Mapping[str, Any],
    str,
    datetime,
    datetime,
]:
    if not isinstance(observation, Mapping):
        raise ValueError("INVALID_CANONICAL_OBSERVATION")

    if observation.get("sport") != expected_sport:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    payload = observation.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("INVALID_HISTORY_EVENT_PAYLOAD")

    source_record_fingerprint = _validate_hex64(
        "SOURCE_RECORD_FINGERPRINT",
        observation.get("record_fingerprint"),
    )
    observed_at = _parse_aware_utc(
        "OBSERVED_AT",
        observation.get("observed_at"),
    )
    available_at = _parse_aware_utc(
        "AVAILABLE_AT",
        observation.get("available_at"),
    )

    if available_at < observed_at:
        raise ValueError(
            "AVAILABLE_AT_BEFORE_OBSERVED_AT"
        )

    return (
        payload,
        source_record_fingerprint,
        observed_at,
        available_at,
    )


def tennis_history_event_from_observation(
    observation: Mapping[str, Any],
) -> TennisHistoryEvent:
    (
        payload,
        source_record_fingerprint,
        observed_at,
        available_at,
    ) = _observation_common(
        observation,
        expected_sport="tennis",
    )

    event_key = _nonempty(
        "EVENT_KEY",
        payload.get("event_key"),
    )
    event_at = _parse_aware_utc(
        "EVENT_AT",
        payload.get("event_at"),
    )
    season_key = _nonempty(
        "SEASON_KEY",
        payload.get("season_key"),
    )
    competition_key = _nonempty(
        "COMPETITION_KEY",
        payload.get("competition_key"),
    )
    opponent_canonical_id = _nonempty(
        "OPPONENT_CANONICAL_ID",
        payload.get("opponent_canonical_id"),
    )

    outcome = payload.get("outcome")
    if outcome not in _ALLOWED_TENNIS_OUTCOMES:
        raise ValueError("INVALID_TENNIS_OUTCOME")

    completed = payload.get("completed")
    if not isinstance(completed, bool):
        raise ValueError("INVALID_COMPLETED_FLAG")

    retirement = payload.get("retirement")
    if not isinstance(retirement, bool):
        raise ValueError("INVALID_RETIREMENT_FLAG")

    surface = payload.get("surface")
    if surface not in _ALLOWED_TENNIS_SURFACES:
        raise ValueError("INVALID_TENNIS_SURFACE")

    indoor = payload.get("indoor")
    if indoor is not None and not isinstance(indoor, bool):
        raise ValueError("INVALID_INDOOR_FLAG")

    if event_at > observed_at:
        raise ValueError(
            "HISTORY_EVENT_AFTER_OBSERVATION"
        )

    metrics = _validate_metrics(
        payload.get("metrics", {})
    )

    base = {
        "schema": "matrix.tennis-history-event/1",
        "event_key": event_key,
        "event_at": _iso(event_at),
        "season_key": season_key,
        "competition_key": competition_key,
        "opponent_canonical_id": opponent_canonical_id,
        "outcome": outcome,
        "completed": completed,
        "retirement": retirement,
        "surface": surface,
        "indoor": indoor,
        "metrics": metrics,
        "source_record_fingerprint": (
            source_record_fingerprint
        ),
        "source_available_at": _iso(available_at),
        "name_join_used": False,
        "missing_is_zero": False,
    }

    return TennisHistoryEvent(
        event_key=event_key,
        event_at=event_at,
        season_key=season_key,
        competition_key=competition_key,
        opponent_canonical_id=opponent_canonical_id,
        outcome=outcome,
        completed=completed,
        retirement=retirement,
        surface=surface,
        indoor=indoor,
        metrics=metrics,
        source_record_fingerprint=(
            source_record_fingerprint
        ),
        source_available_at=available_at,
        event_fingerprint=_sha(base),
    )


def football_history_event_from_observation(
    observation: Mapping[str, Any],
) -> FootballHistoryEvent:
    (
        payload,
        source_record_fingerprint,
        observed_at,
        available_at,
    ) = _observation_common(
        observation,
        expected_sport="football",
    )

    event_key = _nonempty(
        "EVENT_KEY",
        payload.get("event_key"),
    )
    event_at = _parse_aware_utc(
        "EVENT_AT",
        payload.get("event_at"),
    )
    season_key = _nonempty(
        "SEASON_KEY",
        payload.get("season_key"),
    )
    competition_key = _nonempty(
        "COMPETITION_KEY",
        payload.get("competition_key"),
    )
    opponent_canonical_id = _nonempty(
        "OPPONENT_CANONICAL_ID",
        payload.get("opponent_canonical_id"),
    )

    outcome = payload.get("outcome")
    if outcome not in _ALLOWED_FOOTBALL_OUTCOMES:
        raise ValueError("INVALID_FOOTBALL_OUTCOME")

    completed = payload.get("completed")
    if not isinstance(completed, bool):
        raise ValueError("INVALID_COMPLETED_FLAG")

    venue = payload.get("venue")
    if venue not in _ALLOWED_FOOTBALL_VENUES:
        raise ValueError("INVALID_FOOTBALL_VENUE")

    if event_at > observed_at:
        raise ValueError(
            "HISTORY_EVENT_AFTER_OBSERVATION"
        )

    metrics = _validate_metrics(
        payload.get("metrics", {})
    )

    base = {
        "schema": "matrix.football-history-event/1",
        "event_key": event_key,
        "event_at": _iso(event_at),
        "season_key": season_key,
        "competition_key": competition_key,
        "opponent_canonical_id": opponent_canonical_id,
        "outcome": outcome,
        "completed": completed,
        "venue": venue,
        "metrics": metrics,
        "source_record_fingerprint": (
            source_record_fingerprint
        ),
        "source_available_at": _iso(available_at),
        "name_join_used": False,
        "missing_is_zero": False,
    }

    return FootballHistoryEvent(
        event_key=event_key,
        event_at=event_at,
        season_key=season_key,
        competition_key=competition_key,
        opponent_canonical_id=opponent_canonical_id,
        outcome=outcome,
        completed=completed,
        venue=venue,
        metrics=metrics,
        source_record_fingerprint=(
            source_record_fingerprint
        ),
        source_available_at=available_at,
        event_fingerprint=_sha(base),
    )
