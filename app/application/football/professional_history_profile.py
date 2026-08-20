from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping


_FOOTBALL_METRICS = (
    "goals_for",
    "goals_against",
    "xg_for",
    "xg_against",
    "shots",
    "shots_on_target",
    "shots_against",
    "shots_on_target_against",
    "corners_for",
    "corners_against",
    "cards_for",
    "cards_against",
    "possession_pct",
    "first_half_goals_for",
    "first_half_goals_against",
    "second_half_goals_for",
    "second_half_goals_against",
    "first_half_xg_for",
    "first_half_xg_against",
    "second_half_xg_for",
    "second_half_xg_against",
    "first_half_corners_for",
    "first_half_corners_against",
    "second_half_corners_for",
    "second_half_corners_against",
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
    draws = sum(1 for event in values if event.outcome == "D")
    losses = sum(1 for event in values if event.outcome == "L")
    decided = wins + draws + losses

    metric_means: dict[str, float | None] = {}
    metric_coverage: dict[str, int] = {}

    for metric in _FOOTBALL_METRICS:
        observed = [
            float(event.metrics[metric])
            for event in values
            if event.metrics.get(metric) is not None
        ]
        metric_means[metric] = _mean(observed)
        metric_coverage[metric] = len(observed)

    return {
        "sample_size": len(values),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": (
            wins / decided if decided > 0 else None
        ),
        "draw_rate": (
            draws / decided if decided > 0 else None
        ),
        "loss_rate": (
            losses / decided if decided > 0 else None
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
class FootballHistoryProfile:
    sport: str
    canonical_id: str
    as_of: str
    season_key: str
    target_venue: str | None
    target_competition_key: str | None
    segments: Mapping[str, Any]
    source_record_fingerprints: tuple[str, ...]
    history_fingerprint: str
    profile_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.football-history-profile/1",
            "sport": self.sport,
            "canonical_id": self.canonical_id,
            "as_of": self.as_of,
            "season_key": self.season_key,
            "target_venue": self.target_venue,
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


def build_football_history_profile(
    *,
    history,
    target_venue: str | None = None,
    target_competition_key: str | None = None,
) -> FootballHistoryProfile:
    if history.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if (
        target_venue is not None
        and target_venue
        not in {"home", "away", "neutral", "unknown"}
    ):
        raise ValueError("INVALID_FOOTBALL_VENUE")

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

    if target_venue is not None:
        venue_events = tuple(
            event
            for event in events
            if event.venue == target_venue
        )
        segments[
            f"venue:{target_venue}"
        ] = _segment_payload(
            venue_events,
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
        "schema": "matrix.football-history-profile/1",
        "sport": "football",
        "canonical_id": history.canonical_id,
        "as_of": as_of,
        "season_key": history.season_key,
        "target_venue": target_venue,
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

    return FootballHistoryProfile(
        sport="football",
        canonical_id=history.canonical_id,
        as_of=as_of,
        season_key=history.season_key,
        target_venue=target_venue,
        target_competition_key=target_competition_key,
        segments=segments,
        source_record_fingerprints=(
            history.source_record_fingerprints
        ),
        history_fingerprint=history.history_fingerprint,
        profile_fingerprint=_sha(base),
    )
