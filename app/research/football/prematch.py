from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
import unicodedata

from app.research.football.dataset import FootballResearchRow


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class HistoricalFixtureOutcome:
    fixture_id: str
    kickoff_utc: str
    home_team: str
    away_team: str
    competition: str
    country: str
    season: int
    home_goals: int
    away_goals: int
    source_provider: str = "api_football"
    home_team_external_id: str | None = None
    away_team_external_id: str | None = None
    competition_external_id: str | None = None

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not self.home_team.strip() or not self.away_team.strip():
            raise ValueError("fixture/team identity is required")
        if self.home_team == self.away_team:
            raise ValueError("home and away teams must differ")
        _aware(self.kickoff_utc)
        if self.season <= 0:
            raise ValueError("season must be positive")
        for value in (self.home_goals, self.away_goals):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("final scores must be non-negative integers")
        for name in ("home_team_external_id", "away_team_external_id", "competition_external_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty str or None")
        if (self.home_team_external_id is None) != (self.away_team_external_id is None):
            raise ValueError("home/away stable team IDs must be provided as a pair")

    @staticmethod
    def _name_key(value: str) -> str:
        return unicodedata.normalize("NFKC", value).strip().casefold()

    @property
    def home_team_key(self) -> str:
        if self.home_team_external_id is not None:
            return f"{self.source_provider}:team:{self.home_team_external_id.strip()}"
        return f"name:{self._name_key(self.home_team)}"

    @property
    def away_team_key(self) -> str:
        if self.away_team_external_id is not None:
            return f"{self.source_provider}:team:{self.away_team_external_id.strip()}"
        return f"name:{self._name_key(self.away_team)}"

    @property
    def competition_key(self) -> str:
        if self.competition_external_id is not None:
            return f"{self.source_provider}:competition:{self.competition_external_id.strip()}"
        return f"name:{self._name_key(self.competition)}"


@dataclass(frozen=True)
class PrematchFeaturePolicy:
    windows: tuple[int, ...] = (5, 10, 20)
    result_availability_buffer_hours: int = 6
    min_prior_matches: int = 5

    def __post_init__(self) -> None:
        if not self.windows or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in self.windows):
            raise ValueError("windows must contain positive integers")
        if len(set(self.windows)) != len(self.windows):
            raise ValueError("windows must be unique")
        if self.result_availability_buffer_hours < 0:
            raise ValueError("result_availability_buffer_hours cannot be negative")
        if self.min_prior_matches < 0:
            raise ValueError("min_prior_matches cannot be negative")


def _team_view(match: HistoricalFixtureOutcome, team_key: str) -> tuple[int, int, int, str]:
    if match.home_team_key == team_key:
        gf, ga, venue = match.home_goals, match.away_goals, "home"
    elif match.away_team_key == team_key:
        gf, ga, venue = match.away_goals, match.home_goals, "away"
    else:
        raise ValueError("team identity is not part of match")
    points = 3 if gf > ga else 1 if gf == ga else 0
    return gf, ga, points, venue


def _aggregate(matches: list[HistoricalFixtureOutcome], team_key: str) -> dict[str, float | int | None]:
    if not matches:
        return {
            "matches": 0,
            "points_per_match": None,
            "win_rate": None,
            "draw_rate": None,
            "loss_rate": None,
            "goals_for_avg": None,
            "goals_against_avg": None,
            "goal_diff_avg": None,
        }
    views = [_team_view(match, team_key) for match in matches]
    count = len(views)
    points = [row[2] for row in views]
    goals_for = [row[0] for row in views]
    goals_against = [row[1] for row in views]
    return {
        "matches": count,
        "points_per_match": sum(points) / count,
        "win_rate": sum(1 for value in points if value == 3) / count,
        "draw_rate": sum(1 for value in points if value == 1) / count,
        "loss_rate": sum(1 for value in points if value == 0) / count,
        "goals_for_avg": sum(goals_for) / count,
        "goals_against_avg": sum(goals_against) / count,
        "goal_diff_avg": sum(gf - ga for gf, ga, _, _ in views) / count,
    }


def _prefix(prefix: str, values: dict[str, float | int | None]) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in values.items()}


def _labels(match: HistoricalFixtureOutcome) -> dict[str, int | bool | str]:
    total = match.home_goals + match.away_goals
    return {
        "home_win": match.home_goals > match.away_goals,
        "draw": match.home_goals == match.away_goals,
        "away_win": match.home_goals < match.away_goals,
        "btts": match.home_goals > 0 and match.away_goals > 0,
        "over_1_5": total >= 2,
        "over_2_5": total >= 3,
        "over_3_5": total >= 4,
        "final_total_goals": total,
        "full_time_result": "H" if match.home_goals > match.away_goals else "D" if match.home_goals == match.away_goals else "A",
    }


def build_prematch_research_rows(
    fixtures: Iterable[HistoricalFixtureOutcome],
    *,
    policy: PrematchFeaturePolicy = PrematchFeaturePolicy(),
) -> list[FootballResearchRow]:
    ordered = sorted(fixtures, key=lambda item: (_aware(item.kickoff_utc), item.fixture_id))
    history_by_team: dict[str, list[HistoricalFixtureOutcome]] = {}
    rows: list[FootballResearchRow] = []
    buffer = timedelta(hours=policy.result_availability_buffer_hours)

    for target in ordered:
        kickoff = _aware(target.kickoff_utc)

        def eligible(team: str) -> list[HistoricalFixtureOutcome]:
            return [
                prior for prior in history_by_team.get(team, [])
                if _aware(prior.kickoff_utc) + buffer < kickoff
            ]

        home_key = target.home_team_key
        away_key = target.away_team_key
        home_history = eligible(home_key)
        away_history = eligible(away_key)

        if len(home_history) >= policy.min_prior_matches and len(away_history) >= policy.min_prior_matches:
            features: dict[str, int | float | str | bool | None] = {
                "competition": target.competition,
                "country": target.country,
                "season": target.season,
                "home_prior_matches": len(home_history),
                "away_prior_matches": len(away_history),
            }
            for window in sorted(policy.windows):
                home_slice = home_history[-window:]
                away_slice = away_history[-window:]
                features.update(_prefix(f"home_last_{window}", _aggregate(home_slice, home_key)))
                features.update(_prefix(f"away_last_{window}", _aggregate(away_slice, away_key)))

                home_context = [m for m in home_history if m.home_team_key == home_key][-window:]
                away_context = [m for m in away_history if m.away_team_key == away_key][-window:]
                features.update(_prefix(f"home_context_last_{window}", _aggregate(home_context, home_key)))
                features.update(_prefix(f"away_context_last_{window}", _aggregate(away_context, away_key)))

                home_comp = [m for m in home_history if m.competition_key == target.competition_key][-window:]
                away_comp = [m for m in away_history if m.competition_key == target.competition_key][-window:]
                features.update(_prefix(f"home_comp_last_{window}", _aggregate(home_comp, home_key)))
                features.update(_prefix(f"away_comp_last_{window}", _aggregate(away_comp, away_key)))

            home_last = _aware(home_history[-1].kickoff_utc) if home_history else None
            away_last = _aware(away_history[-1].kickoff_utc) if away_history else None
            features["home_rest_hours"] = None if home_last is None else (kickoff - home_last).total_seconds() / 3600.0
            features["away_rest_hours"] = None if away_last is None else (kickoff - away_last).total_seconds() / 3600.0

            # Labels are deliberately timestamped after a conservative result-availability
            # buffer. Features only use older matches whose own buffer has elapsed.
            rows.append(
                FootballResearchRow(
                    fixture_id=target.fixture_id,
                    as_of_utc=kickoff.isoformat(),
                    partition="train",
                    features=features,
                    labels=_labels(target),
                    label_observed_at_utc=(kickoff + buffer).isoformat(),
                    source_provider=target.source_provider,
                )
            )

        history_by_team.setdefault(target.home_team_key, []).append(target)
        history_by_team.setdefault(target.away_team_key, []).append(target)

    return rows
