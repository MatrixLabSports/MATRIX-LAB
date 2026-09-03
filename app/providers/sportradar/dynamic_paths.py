from __future__ import annotations

from datetime import date as date_type
import re
from typing import Sequence

from app.core.provider_request_contract import RequestParameterRule
from app.providers.sportradar.config import SportradarConfig


_ID_PATTERNS = {
    "competition": re.compile(r"^sr:competition:[1-9][0-9]*$"),
    "season": re.compile(r"^sr:season:[1-9][0-9]*$"),
    "sport_event": re.compile(r"^sr:sport_event:[1-9][0-9]*$"),
}


def _resource_id(kind: str, value: object) -> str:
    pattern = _ID_PATTERNS.get(kind)
    if pattern is None:
        raise ValueError("INVALID_SPORTRADAR_RESOURCE_KIND")
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"INVALID_SPORTRADAR_{kind.upper()}_ID")
    return value


def _date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("INVALID_SPORTRADAR_DATE")
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as error:
        raise ValueError("INVALID_SPORTRADAR_DATE") from error
    if parsed.isoformat() != value:
        raise ValueError("INVALID_SPORTRADAR_DATE")
    return value


def _prefix(config: SportradarConfig, sport: str) -> str:
    if sport == "tennis":
        product = "tennis"
        version = config.tennis_version
    elif sport == "football":
        product = "soccer"
        version = config.soccer_version
    else:
        raise ValueError("INVALID_SPORTRADAR_SPORT")
    language_code = config._language_for_sport(sport)
    return (
        f"/{product}/{config.access_level}/{version}/"
        f"{language_code}"
    )


def build_sportradar_dynamic_path(
    *,
    config: SportradarConfig,
    sport: str,
    feed: str,
    resource_id: str | None = None,
    date: str | None = None,
) -> str:
    prefix = _prefix(config, sport)

    if sport == "tennis":
        if feed == "competition_seasons":
            rid = _resource_id("competition", resource_id)
            return f"{prefix}/competitions/{rid}/seasons.json"
        if feed == "season_summaries":
            rid = _resource_id("season", resource_id)
            return f"{prefix}/seasons/{rid}/summaries.json"
        if feed == "daily_summaries":
            day = _date(date)
            return f"{prefix}/schedules/{day}/summaries.json"
        if feed == "sport_event_summary":
            rid = _resource_id("sport_event", resource_id)
            return f"{prefix}/sport_events/{rid}/summary.json"

    if sport == "football":
        if feed == "season_schedule":
            rid = _resource_id("season", resource_id)
            return f"{prefix}/seasons/{rid}/schedules.json"
        if feed == "daily_schedule":
            day = _date(date)
            return f"{prefix}/schedules/{day}/schedules.json"
        if feed == "sport_event_timeline":
            rid = _resource_id("sport_event", resource_id)
            return f"{prefix}/sport_events/{rid}/timeline.json"

    raise ValueError("UNSUPPORTED_SPORTRADAR_DYNAMIC_FEED")


def sportradar_dynamic_parameter_rules(
    *,
    sport: str,
    feed: str,
) -> Sequence[RequestParameterRule]:
    if sport == "tennis" and feed == "season_summaries":
        return (
            RequestParameterRule(
                name="start",
                value_type="POSITIVE_INT",
                required=False,
                minimum=1,
                maximum=1000000,
            ),
            RequestParameterRule(
                name="limit",
                value_type="POSITIVE_INT",
                required=False,
                minimum=1,
                maximum=200,
            ),
        )
    return ()
