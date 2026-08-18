from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _non_empty(value: Any, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} cannot be empty")
    return text


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("match_date must be ISO YYYY-MM-DD") from exc


def _sha256_hex(value: str, name: str) -> str:
    text = _non_empty(value, name).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{name} must be 64 lowercase/uppercase hex characters")
    return text


@dataclass(frozen=True)
class FootballHistoryObservation:
    fixture_id: str
    kickoff_utc: str | None
    team_id: str
    team_name: str
    opponent_id: str | None
    opponent_name: str
    venue_role: str
    goals_for: int
    goals_against: int
    competition: str | None
    source_provider: str
    observed_at_utc: str
    source_payload_sha256: str | None = None
    match_date: str | None = None
    time_precision: str = "datetime"
    fixture_identity_kind: str = "provider"
    source_team_id: str | None = None
    source_opponent_id: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        for name in ("fixture_id", "team_id", "team_name", "opponent_name", "source_provider"):
            _non_empty(getattr(self, name), name)
        if self.venue_role not in {"home", "away"}:
            raise ValueError("venue_role must be home or away")
        if self.time_precision not in {"datetime", "date"}:
            raise ValueError("time_precision must be datetime or date")
        observed = _utc(self.observed_at_utc)
        if self.time_precision == "datetime":
            if self.kickoff_utc is None:
                raise ValueError("kickoff_utc is required for datetime precision")
            kickoff = _utc(self.kickoff_utc)
            if observed < kickoff:
                raise ValueError("history result observed_at cannot predate kickoff")
            if self.match_date is not None and _iso_date(self.match_date) != kickoff.date():
                raise ValueError("match_date conflicts with kickoff_utc")
        else:
            if self.kickoff_utc is not None:
                raise ValueError("date-precision history must not invent kickoff_utc")
            if self.match_date is None:
                raise ValueError("match_date is required for date precision")
            match_day = _iso_date(self.match_date)
            if observed.date() < match_day:
                raise ValueError("history result observed_at cannot predate match_date")
        for name in ("goals_for", "goals_against"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.source_payload_sha256 is not None:
            _sha256_hex(self.source_payload_sha256, "source_payload_sha256")
        if self.fixture_identity_kind not in {"provider", "derived"}:
            raise ValueError("fixture_identity_kind must be provider or derived")
        if self.source_reference is not None and not str(self.source_reference).strip():
            raise ValueError("source_reference cannot be blank")

    def effective_match_date(self) -> date:
        if self.time_precision == "datetime":
            assert self.kickoff_utc is not None
            return _utc(self.kickoff_utc).date()
        assert self.match_date is not None
        return _iso_date(self.match_date)


@dataclass(frozen=True)
class FootballMatchAnalysisInput:
    benchmark_id: str
    target_key: str
    fixture_id: str
    as_of_utc: str
    kickoff_utc: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    competition_id: str | None
    competition_name: str
    season: int | None
    round_name: str | None
    venue_name: str | None
    fixture_source_provider: str
    fixture_payload_sha256: str
    fixture_id_namespace: str = "provider"
    home_team_id_namespace: str = "provider"
    away_team_id_namespace: str = "provider"
    home_history: tuple[FootballHistoryObservation, ...] = ()
    away_history: tuple[FootballHistoryObservation, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "benchmark_id", "target_key", "fixture_id", "home_team_id", "home_team_name",
            "away_team_id", "away_team_name", "competition_name", "fixture_source_provider",
        ):
            _non_empty(getattr(self, name), name)
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away team IDs must differ")
        as_of = _utc(self.as_of_utc)
        kickoff = _utc(self.kickoff_utc)
        if as_of >= kickoff:
            raise ValueError("analysis input must be frozen strictly before kickoff")
        _sha256_hex(self.fixture_payload_sha256, "fixture_payload_sha256")
        for name in ("fixture_id_namespace", "home_team_id_namespace", "away_team_id_namespace"):
            _non_empty(getattr(self, name), name)
        if self.season is not None and (isinstance(self.season, bool) or not isinstance(self.season, int) or self.season <= 0):
            raise ValueError("season must be a positive integer or None")
        self._validate_history(self.home_history, self.home_team_id, kickoff, as_of, "home")
        self._validate_history(self.away_history, self.away_team_id, kickoff, as_of, "away")

    @staticmethod
    def _validate_history(
        rows: tuple[FootballHistoryObservation, ...],
        team_id: str,
        target_kickoff: datetime,
        analysis_as_of: datetime,
        side: str,
    ) -> None:
        fixture_ids: set[str] = set()
        for row in rows:
            if row.team_id != team_id:
                raise ValueError(f"{side} history contains another team")
            if row.time_precision == "datetime":
                assert row.kickoff_utc is not None
                if _utc(row.kickoff_utc) >= target_kickoff:
                    raise ValueError(f"{side} history leaks target/future fixture")
            else:
                # Conservative rule for date-only sources: same-day rows are excluded because
                # their true kickoff ordering is unknown.
                if row.effective_match_date() >= target_kickoff.date():
                    raise ValueError(f"{side} date-only history leaks target/future fixture")
            observed_at = _utc(row.observed_at_utc)
            if observed_at >= target_kickoff:
                raise ValueError(f"{side} history was observed too late for pre-match analysis")
            if observed_at > analysis_as_of:
                raise ValueError(f"{side} history was observed after analysis as_of")
            if row.fixture_id in fixture_ids:
                raise ValueError(f"duplicate fixture in {side} history")
            fixture_ids.add(row.fixture_id)

    def canonical_sha256(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FootballAnalysisReadinessPolicy:
    min_history_per_team: int = 5
    preferred_history_per_team: int = 20
    require_stable_ids: bool = True
    require_prematch_freeze: bool = True

    def __post_init__(self) -> None:
        if self.min_history_per_team < 0:
            raise ValueError("min_history_per_team cannot be negative")
        if self.preferred_history_per_team < self.min_history_per_team:
            raise ValueError("preferred_history_per_team must be >= min_history_per_team")


@dataclass(frozen=True)
class FootballAnalysisReadiness:
    target_key: str
    status: str
    coverage_score: float
    home_history_count: int
    away_history_count: int
    missing_critical: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == "READY_FOR_EXPERIMENTAL_EVALUATION"


def assess_match_analysis_readiness(
    value: FootballMatchAnalysisInput,
    *,
    policy: FootballAnalysisReadinessPolicy = FootballAnalysisReadinessPolicy(),
) -> FootballAnalysisReadiness:
    missing: list[str] = []
    warnings: list[str] = []
    home_count = len(value.home_history)
    away_count = len(value.away_history)

    if policy.require_stable_ids:
        for name in ("fixture_id", "home_team_id", "away_team_id"):
            if not str(getattr(value, name)).strip():
                missing.append(name)
    if home_count < policy.min_history_per_team:
        missing.append("home_history")
    if away_count < policy.min_history_per_team:
        missing.append("away_history")
    if home_count < policy.preferred_history_per_team:
        warnings.append("home_history_below_preferred")
    if away_count < policy.preferred_history_per_team:
        warnings.append("away_history_below_preferred")

    combined_history = value.home_history + value.away_history
    providers = {row.source_provider for row in combined_history}
    if any(row.time_precision == "date" for row in combined_history):
        warnings.append("date_only_history_precision")
    if any(row.fixture_identity_kind == "derived" for row in combined_history):
        warnings.append("derived_history_identity")
    if providers and (providers != {value.fixture_source_provider}):
        warnings.append("supplemental_or_mixed_history_sources")
    if value.fixture_id_namespace != "api_football":
        warnings.append("non_primary_fixture_identity")

    # Coverage is intentionally interpretable rather than presented as model confidence.
    identity_weight = 0.30
    history_weight = 0.70
    identity_fraction = 1.0
    preferred = max(policy.preferred_history_per_team, 1)
    history_fraction = (min(home_count, preferred) + min(away_count, preferred)) / (2 * preferred)
    coverage = identity_weight * identity_fraction + history_weight * history_fraction
    status = "READY_FOR_EXPERIMENTAL_EVALUATION" if not missing else "INSUFFICIENT_DATA"
    return FootballAnalysisReadiness(
        target_key=value.target_key,
        status=status,
        coverage_score=round(coverage, 6),
        home_history_count=home_count,
        away_history_count=away_count,
        missing_critical=tuple(sorted(set(missing))),
        warnings=tuple(sorted(set(warnings))),
    )


def _history_side(
    raw_side: Mapping[str, Any] | None,
    *,
    team_id: str,
    team_name: str,
    source_provider: str,
) -> tuple[FootballHistoryObservation, ...]:
    if not isinstance(raw_side, Mapping):
        return ()
    observed_at = raw_side.get("observed_at_utc")
    rows = raw_side.get("completed_before_target")
    if not observed_at or not isinstance(rows, list):
        return ()

    output: list[FootballHistoryObservation] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        home_id = None if raw.get("home_team_id") is None else str(raw.get("home_team_id"))
        away_id = None if raw.get("away_team_id") is None else str(raw.get("away_team_id"))
        home_name = str(raw.get("home_team") or "").strip()
        away_name = str(raw.get("away_team") or "").strip()
        focal_is_home = home_id == team_id
        if focal_is_home:
            gf, ga = raw.get("home_goals"), raw.get("away_goals")
            opponent_id, opponent_name, role = away_id, away_name, "home"
        elif away_id == team_id:
            gf, ga = raw.get("away_goals"), raw.get("home_goals")
            opponent_id, opponent_name, role = home_id, home_name, "away"
        else:
            raise ValueError(f"history fixture does not contain expected team {team_name}")
        if isinstance(gf, bool) or isinstance(ga, bool) or not isinstance(gf, int) or not isinstance(ga, int):
            raise ValueError("history final goals must be integers")
        output.append(
            FootballHistoryObservation(
                fixture_id=_non_empty(raw.get("fixture_id"), "history.fixture_id"),
                kickoff_utc=_non_empty(raw.get("kickoff_utc"), "history.kickoff_utc"),
                team_id=team_id,
                team_name=team_name,
                opponent_id=opponent_id,
                opponent_name=_non_empty(opponent_name, "history.opponent_name"),
                venue_role=role,
                goals_for=gf,
                goals_against=ga,
                competition=None if raw.get("competition") is None else str(raw.get("competition")),
                source_provider=source_provider,
                observed_at_utc=str(observed_at),
                source_payload_sha256=None if raw.get("source_payload_sha256") is None else str(raw.get("source_payload_sha256")),
                source_reference=None if raw.get("source_reference") is None else str(raw.get("source_reference")),
            )
        )
    output.sort(key=lambda row: row.effective_match_date(), reverse=True)
    return tuple(output)


def build_match_analysis_inputs_from_benchmark(
    document: Mapping[str, Any],
) -> tuple[tuple[FootballMatchAnalysisInput, ...], tuple[str, ...]]:
    benchmark_id = _non_empty(document.get("benchmark_id"), "benchmark_id")
    provider = _non_empty(document.get("provider"), "provider")
    fixtures = document.get("fixtures")
    histories = document.get("histories")
    if not isinstance(fixtures, Mapping):
        raise ValueError("benchmark fixtures must be an object")
    histories = histories if isinstance(histories, Mapping) else {}

    inputs: list[FootballMatchAnalysisInput] = []
    rejected: list[str] = []
    for target_key, raw in sorted(fixtures.items()):
        if not isinstance(raw, Mapping):
            rejected.append(str(target_key))
            continue
        if raw.get("pre_match_frozen") is not True:
            rejected.append(str(target_key))
            continue
        home = raw.get("home") if isinstance(raw.get("home"), Mapping) else {}
        away = raw.get("away") if isinstance(raw.get("away"), Mapping) else {}
        league = raw.get("league") if isinstance(raw.get("league"), Mapping) else {}
        venue = raw.get("venue") if isinstance(raw.get("venue"), Mapping) else {}
        target_histories = histories.get(target_key) if isinstance(histories.get(target_key), Mapping) else {}
        home_id = _non_empty(home.get("id"), "home.id")
        away_id = _non_empty(away.get("id"), "away.id")
        home_name = _non_empty(home.get("name"), "home.name")
        away_name = _non_empty(away.get("name"), "away.name")
        kickoff = _non_empty(raw.get("kickoff_utc"), "kickoff_utc")
        value = FootballMatchAnalysisInput(
            benchmark_id=benchmark_id,
            target_key=str(target_key),
            fixture_id=_non_empty(raw.get("fixture_id"), "fixture_id"),
            as_of_utc=_non_empty(raw.get("observed_at_utc"), "observed_at_utc"),
            kickoff_utc=kickoff,
            home_team_id=home_id,
            home_team_name=home_name,
            away_team_id=away_id,
            away_team_name=away_name,
            competition_id=None if league.get("id") is None else str(league.get("id")),
            competition_name=_non_empty(league.get("name"), "league.name"),
            season=None if league.get("season") is None else int(league.get("season")),
            round_name=None if league.get("round") is None else str(league.get("round")),
            venue_name=None if venue.get("name") is None else str(venue.get("name")),
            fixture_source_provider=provider,
            fixture_payload_sha256=_non_empty(raw.get("source_payload_sha256"), "source_payload_sha256"),
            fixture_id_namespace=provider,
            home_team_id_namespace=provider,
            away_team_id_namespace=provider,
            home_history=_history_side(
                target_histories.get("home") if isinstance(target_histories, Mapping) else None,
                team_id=home_id, team_name=home_name, source_provider=provider,
            ),
            away_history=_history_side(
                target_histories.get("away") if isinstance(target_histories, Mapping) else None,
                team_id=away_id, team_name=away_name, source_provider=provider,
            ),
        )
        inputs.append(value)

    unresolved = document.get("unresolved_targets")
    if isinstance(unresolved, list):
        rejected.extend(str(item) for item in unresolved)
    return tuple(inputs), tuple(sorted(set(rejected)))
