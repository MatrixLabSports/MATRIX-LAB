from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.providers.api_football.live_service import (
    ApiFootballLiveBundle,
)


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _int(value: object) -> int | None:
    parsed = _number(value)
    if parsed is None:
        return None
    if not parsed.is_integer():
        return None
    return int(parsed)


def _stat_key(value: object) -> str:
    return "".join(
        character
        for character in str(value).lower()
        if character.isalnum()
    )


_STAT_MAP = {
    "shotsongoal": "shots_on_goal",
    "shotsoffgoal": "shots_off_goal",
    "totalshots": "total_shots",
    "blockedshots": "blocked_shots",
    "shotsinsidebox": "shots_inside_box",
    "shotsoutsidebox": "shots_outside_box",
    "fouls": "fouls",
    "cornerkicks": "corners",
    "offsides": "offsides",
    "ballpossession": "possession_pct",
    "yellowcards": "yellow_cards",
    "redcards": "red_cards",
    "goalkeepersaves": "goalkeeper_saves",
    "totalpasses": "total_passes",
    "passesaccurate": "accurate_passes",
    "passes": "pass_accuracy_pct",
    "passespercentage": "pass_accuracy_pct",
    "passespercent": "pass_accuracy_pct",
}


@dataclass(frozen=True)
class TeamLiveStatistics:
    team_id: int | None
    team_name: str
    shots_on_goal: float | None = None
    shots_off_goal: float | None = None
    total_shots: float | None = None
    blocked_shots: float | None = None
    shots_inside_box: float | None = None
    shots_outside_box: float | None = None
    fouls: float | None = None
    corners: float | None = None
    offsides: float | None = None
    possession_pct: float | None = None
    yellow_cards: float | None = None
    red_cards: float | None = None
    goalkeeper_saves: float | None = None
    total_passes: float | None = None
    accurate_passes: float | None = None
    pass_accuracy_pct: float | None = None

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FootballLiveSnapshot:
    provider: str
    fixture_id: int
    captured_at: datetime
    status_short: str | None
    elapsed_minute: int | None
    home_team_id: int | None
    home_team_name: str
    away_team_id: int | None
    away_team_name: str
    home_goals: int | None
    away_goals: int | None
    home_statistics: TeamLiveStatistics
    away_statistics: TeamLiveStatistics
    event_count: int
    live_odds_item_count: int
    payload_fingerprints: Mapping[str, str]
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.provider != "api_football":
            raise ValueError(
                "FOOTBALL_LIVE_PROVIDER_SCOPE_INVALID"
            )
        if self.automatic_wagering is not False:
            raise ValueError(
                "AUTOMATIC_WAGERING_FORBIDDEN"
            )

    def payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "fixture_id": self.fixture_id,
            "captured_at": self.captured_at.isoformat(),
            "status_short": self.status_short,
            "elapsed_minute": self.elapsed_minute,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_statistics": (
                self.home_statistics.payload()
            ),
            "away_statistics": (
                self.away_statistics.payload()
            ),
            "event_count": self.event_count,
            "live_odds_item_count": (
                self.live_odds_item_count
            ),
            "payload_fingerprints": dict(
                sorted(
                    self.payload_fingerprints.items()
                )
            ),
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class FootballLivePressureFeatures:
    possession_delta_home: float | None
    total_shots_delta_home: float | None
    shots_on_goal_delta_home: float | None
    shots_inside_box_delta_home: float | None
    corners_delta_home: float | None
    pass_accuracy_delta_home: float | None
    home_shot_share: float | None
    home_shots_on_goal_share: float | None
    home_box_shot_share: float | None
    home_corner_share: float | None

    def payload(self) -> dict[str, object]:
        return asdict(self)


def _team_identity(
    fixture: Mapping[str, Any],
    side: str,
) -> tuple[int | None, str]:
    teams = fixture.get("teams")
    if not isinstance(teams, Mapping):
        raise ValueError(
            "API_FOOTBALL_LIVE_TEAMS_REQUIRED"
        )
    team = teams.get(side)
    if not isinstance(team, Mapping):
        raise ValueError(
            "API_FOOTBALL_LIVE_TEAM_REQUIRED"
        )
    team_id = _int(team.get("id"))
    name = str(team.get("name") or "").strip()
    if not name:
        raise ValueError(
            "API_FOOTBALL_LIVE_TEAM_NAME_REQUIRED"
        )
    return team_id, name


def _team_stats(
    statistics: Sequence[Mapping[str, Any]],
    *,
    team_id: int | None,
    team_name: str,
) -> TeamLiveStatistics:
    values: dict[str, float | None] = {}

    for row in statistics:
        team = row.get("team")
        if not isinstance(team, Mapping):
            continue

        row_id = _int(team.get("id"))
        row_name = str(team.get("name") or "").strip()

        matches = (
            team_id is not None
            and row_id == team_id
        ) or (
            team_id is None
            and row_name
            and row_name == team_name
        )
        if not matches:
            continue

        raw_stats = row.get("statistics")
        if not isinstance(raw_stats, Sequence):
            continue

        for item in raw_stats:
            if not isinstance(item, Mapping):
                continue
            field = _STAT_MAP.get(
                _stat_key(item.get("type"))
            )
            if field is None:
                continue
            values[field] = _number(
                item.get("value")
            )

    return TeamLiveStatistics(
        team_id=team_id,
        team_name=team_name,
        **values,
    )


def snapshot_from_api_football_bundle(
    bundle: ApiFootballLiveBundle,
) -> FootballLiveSnapshot:
    fixture = bundle.fixture
    home_id, home_name = _team_identity(
        fixture,
        "home",
    )
    away_id, away_name = _team_identity(
        fixture,
        "away",
    )

    fixture_meta = fixture.get("fixture")
    status = (
        fixture_meta.get("status")
        if isinstance(fixture_meta, Mapping)
        else None
    )
    if not isinstance(status, Mapping):
        status = {}

    goals = fixture.get("goals")
    if not isinstance(goals, Mapping):
        goals = {}

    return FootballLiveSnapshot(
        provider="api_football",
        fixture_id=bundle.fixture_id,
        captured_at=bundle.captured_at,
        status_short=(
            str(status.get("short")).strip()
            if status.get("short") is not None
            else None
        ),
        elapsed_minute=_int(
            status.get("elapsed")
        ),
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        home_goals=_int(goals.get("home")),
        away_goals=_int(goals.get("away")),
        home_statistics=_team_stats(
            bundle.statistics,
            team_id=home_id,
            team_name=home_name,
        ),
        away_statistics=_team_stats(
            bundle.statistics,
            team_id=away_id,
            team_name=away_name,
        ),
        event_count=len(bundle.events),
        live_odds_item_count=len(
            bundle.live_odds
        ),
        payload_fingerprints=(
            bundle.payload_fingerprints
        ),
    )


def _delta(
    home: float | None,
    away: float | None,
) -> float | None:
    if home is None or away is None:
        return None
    return home - away


def _share(
    home: float | None,
    away: float | None,
) -> float | None:
    if home is None or away is None:
        return None
    total = home + away
    if total <= 0:
        return None
    return home / total


def derive_live_pressure_features(
    snapshot: FootballLiveSnapshot,
) -> FootballLivePressureFeatures:
    home = snapshot.home_statistics
    away = snapshot.away_statistics

    return FootballLivePressureFeatures(
        possession_delta_home=_delta(
            home.possession_pct,
            away.possession_pct,
        ),
        total_shots_delta_home=_delta(
            home.total_shots,
            away.total_shots,
        ),
        shots_on_goal_delta_home=_delta(
            home.shots_on_goal,
            away.shots_on_goal,
        ),
        shots_inside_box_delta_home=_delta(
            home.shots_inside_box,
            away.shots_inside_box,
        ),
        corners_delta_home=_delta(
            home.corners,
            away.corners,
        ),
        pass_accuracy_delta_home=_delta(
            home.pass_accuracy_pct,
            away.pass_accuracy_pct,
        ),
        home_shot_share=_share(
            home.total_shots,
            away.total_shots,
        ),
        home_shots_on_goal_share=_share(
            home.shots_on_goal,
            away.shots_on_goal,
        ),
        home_box_shot_share=_share(
            home.shots_inside_box,
            away.shots_inside_box,
        ),
        home_corner_share=_share(
            home.corners,
            away.corners,
        ),
    )
