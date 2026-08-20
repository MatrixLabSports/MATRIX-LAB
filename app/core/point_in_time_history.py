from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
_DEFAULT_WINDOWS = (5, 10, 20, 30, 50)


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


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _validate_windows(
    windows: Sequence[int],
) -> tuple[int, ...]:
    if (
        isinstance(windows, (str, bytes))
        or not isinstance(windows, Sequence)
    ):
        raise ValueError("INVALID_HISTORY_WINDOWS")

    normalized = tuple(sorted(set(windows)))

    if not normalized:
        raise ValueError("EMPTY_HISTORY_WINDOWS")

    for value in normalized:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            or value > 500
        ):
            raise ValueError("INVALID_HISTORY_WINDOW")

    return normalized


@dataclass(frozen=True)
class PointInTimeHistory:
    sport: str
    canonical_id: str
    as_of: datetime
    season_key: str
    windows: tuple[tuple[int, tuple[Any, ...]], ...]
    season: tuple[Any, ...]
    career: tuple[Any, ...]
    source_record_fingerprints: tuple[str, ...]
    history_fingerprint: str

    def window(self, size: int) -> tuple[Any, ...]:
        for window_size, events in self.windows:
            if window_size == size:
                return events
        raise KeyError(size)


def _deduplicate_latest_as_of(
    events: Iterable[Any],
    *,
    as_of: datetime,
) -> tuple[Any, ...]:
    latest_by_key: dict[str, Any] = {}

    for event in events:
        if event.source_available_at > as_of:
            continue

        if event.event_at >= as_of:
            continue

        if event.completed is not True:
            continue

        current = latest_by_key.get(event.event_key)
        if current is None:
            latest_by_key[event.event_key] = event
            continue

        if (
            event.source_available_at
            > current.source_available_at
        ):
            latest_by_key[event.event_key] = event
            continue

        if (
            event.source_available_at
            == current.source_available_at
            and event.event_fingerprint
            != current.event_fingerprint
        ):
            raise ValueError(
                "AMBIGUOUS_HISTORY_CORRECTION_AS_OF"
            )

    return tuple(
        sorted(
            latest_by_key.values(),
            key=lambda item: (
                item.event_at,
                item.event_key,
            ),
            reverse=True,
        )
    )


def build_point_in_time_history(
    *,
    sport: str,
    canonical_id: str,
    events: Iterable[Any],
    as_of: datetime,
    season_key: str,
    windows: Sequence[int] = _DEFAULT_WINDOWS,
) -> PointInTimeHistory:
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")

    if not isinstance(canonical_id, str) or not canonical_id:
        raise ValueError("INVALID_CANONICAL_ID")

    if not isinstance(season_key, str) or not season_key:
        raise ValueError("INVALID_SEASON_KEY")

    as_of = _aware_utc("AS_OF", as_of)
    windows = _validate_windows(windows)

    career = _deduplicate_latest_as_of(
        events,
        as_of=as_of,
    )
    season = tuple(
        event
        for event in career
        if event.season_key == season_key
    )
    window_sets = tuple(
        (size, career[:size])
        for size in windows
    )
    source_fingerprints = tuple(
        sorted(
            {
                event.source_record_fingerprint
                for event in career
            }
        )
    )

    base = {
        "schema": "matrix.point-in-time-history/1",
        "sport": sport,
        "canonical_id": canonical_id,
        "as_of": _iso(as_of),
        "season_key": season_key,
        "windows": [
            {
                "size": size,
                "event_fingerprints": [
                    event.event_fingerprint
                    for event in values
                ],
            }
            for size, values in window_sets
        ],
        "season_event_fingerprints": [
            event.event_fingerprint
            for event in season
        ],
        "career_event_fingerprints": [
            event.event_fingerprint
            for event in career
        ],
        "source_record_fingerprints": list(
            source_fingerprints
        ),
        "future_leakage_allowed": False,
        "missing_is_zero": False,
        "name_join_used": False,
    }

    return PointInTimeHistory(
        sport=sport,
        canonical_id=canonical_id,
        as_of=as_of,
        season_key=season_key,
        windows=window_sets,
        season=season,
        career=career,
        source_record_fingerprints=source_fingerprints,
        history_fingerprint=_sha(base),
    )
