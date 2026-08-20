from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping


_TENNIS_METRICS = (
    "aces",
    "double_faults",
    "first_serve_in_pct",
    "first_serve_points_won_pct",
    "second_serve_points_won_pct",
    "service_points_won_pct",
    "hold_pct",
    "break_points_saved_pct",
    "return_points_won_pct",
    "return_first_serve_points_won_pct",
    "return_second_serve_points_won_pct",
    "break_points_created",
    "break_points_converted_pct",
    "break_pct",
    "tie_break_win_pct",
    "match_duration_minutes",
)


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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _summarize(events: Iterable[Any]) -> Mapping[str, Any]:
    values = tuple(events)
    wins = sum(1 for event in values if event.outcome == "W")
    losses = sum(1 for event in values if event.outcome == "L")
    retirements = sum(
        1 for event in values if event.retirement
    )

    metric_means: dict[str, float | None] = {}
    metric_coverage: dict[str, int] = {}

    for metric in _TENNIS_METRICS:
        observed = [
            float(event.metrics[metric])
            for event in values
            if event.metrics.get(metric) is not None
        ]
        metric_means[metric] = _mean(observed)
        metric_coverage[metric] = len(observed)

    decided = wins + losses

    return {
        "sample_size": len(values),
        "wins": wins,
        "losses": losses,
        "win_rate": (
            wins / decided
            if decided > 0
            else None
        ),
        "retirements": retirements,
        "retirement_rate": (
            retirements / len(values)
            if values
            else None
        ),
        "metric_means": metric_means,
        "metric_coverage": metric_coverage,
        "recency_weighting_applied": False,
    }


def _segment_payload(
    events: tuple[Any, ...],
    *,
    season_key: str,
    windows: tuple[int, ...],
) -> Mapping[str, Any]:
    return {
        "windows": {
            str(size): _summarize(events[:size])
            for size in windows
        },
        "season": _summarize(
            event
            for event in events
            if event.season_key == season_key
        ),
        "career": _summarize(events),
    }


@dataclass(frozen=True)
class TennisHistoryProfile:
    sport: str
    canonical_id: str
    as_of: str
    season_key: str
    target_surface: str | None
    target_indoor: bool | None
    target_competition_key: str | None
    segments: Mapping[str, Any]
    source_record_fingerprints: tuple[str, ...]
    history_fingerprint: str
    profile_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.tennis-history-profile/1",
            "sport": self.sport,
            "canonical_id": self.canonical_id,
            "as_of": self.as_of,
            "season_key": self.season_key,
            "target_surface": self.target_surface,
            "target_indoor": self.target_indoor,
            "target_competition_key": (
                self.target_competition_key
            ),
            "segments": self.segments,
            "source_record_fingerprints": list(
                self.source_record_fingerprints
            ),
            "history_fingerprint": self.history_fingerprint,
            "profile_fingerprint": self.profile_fingerprint,
            "recency_weighting_applied": False,
            "point_in_time_enforced": True,
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def build_tennis_history_profile(
    *,
    history,
    target_surface: str | None = None,
    target_indoor: bool | None = None,
    target_competition_key: str | None = None,
) -> TennisHistoryProfile:
    if history.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    allowed_surfaces = {
        "hard",
        "clay",
        "grass",
        "carpet",
        "unknown",
    }
    if (
        target_surface is not None
        and target_surface not in allowed_surfaces
    ):
        raise ValueError("INVALID_TENNIS_SURFACE")

    if (
        target_indoor is not None
        and not isinstance(target_indoor, bool)
    ):
        raise ValueError("INVALID_INDOOR_FLAG")

    if (
        target_competition_key is not None
        and (
            not isinstance(target_competition_key, str)
            or not target_competition_key
        )
    ):
        raise ValueError("INVALID_COMPETITION_KEY")

    events = tuple(history.career)
    windows = tuple(
        size for size, _ in history.windows
    )

    segments: dict[str, Any] = {
        "overall": _segment_payload(
            events,
            season_key=history.season_key,
            windows=windows,
        )
    }

    if target_surface is not None:
        surface_events = tuple(
            event
            for event in events
            if event.surface == target_surface
        )
        segments[
            f"surface:{target_surface}"
        ] = _segment_payload(
            surface_events,
            season_key=history.season_key,
            windows=windows,
        )

    if target_indoor is not None:
        indoor_events = tuple(
            event
            for event in events
            if event.indoor is target_indoor
        )
        environment = (
            "indoor" if target_indoor else "outdoor"
        )
        segments[
            f"environment:{environment}"
        ] = _segment_payload(
            indoor_events,
            season_key=history.season_key,
            windows=windows,
        )

    if target_competition_key is not None:
        competition_events = tuple(
            event
            for event in events
            if (
                event.competition_key
                == target_competition_key
            )
        )
        segments[
            f"competition:{target_competition_key}"
        ] = _segment_payload(
            competition_events,
            season_key=history.season_key,
            windows=windows,
        )

    as_of = (
        history.as_of.isoformat()
        .replace("+00:00", "Z")
    )

    base = {
        "schema": "matrix.tennis-history-profile/1",
        "sport": "tennis",
        "canonical_id": history.canonical_id,
        "as_of": as_of,
        "season_key": history.season_key,
        "target_surface": target_surface,
        "target_indoor": target_indoor,
        "target_competition_key": target_competition_key,
        "segments": segments,
        "source_record_fingerprints": list(
            history.source_record_fingerprints
        ),
        "history_fingerprint": history.history_fingerprint,
        "recency_weighting_applied": False,
        "point_in_time_enforced": True,
        "missing_is_zero": False,
        "name_join_used": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return TennisHistoryProfile(
        sport="tennis",
        canonical_id=history.canonical_id,
        as_of=as_of,
        season_key=history.season_key,
        target_surface=target_surface,
        target_indoor=target_indoor,
        target_competition_key=target_competition_key,
        segments=segments,
        source_record_fingerprints=(
            history.source_record_fingerprints
        ),
        history_fingerprint=history.history_fingerprint,
        profile_fingerprint=_sha(base),
    )
