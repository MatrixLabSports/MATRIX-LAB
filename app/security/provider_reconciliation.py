from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256
from app.security.provider_normalization import CanonicalFixtureIdentity


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _nonempty(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _int(value: int, name: str, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


class EventState(str, Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, order=True)
class MarketIdentity:
    market_type: str
    period: str
    selection: str
    line_milli: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.market_type, "market_type"),
            (self.period, "period"),
            (self.selection, "selection"),
        ):
            _nonempty(value, name)
        if self.line_milli is not None and (isinstance(self.line_milli, bool) or not isinstance(self.line_milli, int)):
            raise TypeError("line_milli must be int or None")

    @property
    def key(self) -> str:
        line = "NA" if self.line_milli is None else str(self.line_milli)
        return f"{self.market_type}|{self.period}|{self.selection}|{line}"


@dataclass(frozen=True, order=True)
class StatisticValue:
    metric_id: str
    home_value: int
    away_value: int

    def __post_init__(self) -> None:
        _nonempty(self.metric_id, "metric_id")
        _int(self.home_value, "home_value")
        _int(self.away_value, "away_value")


@dataclass(frozen=True)
class ProviderEventSnapshot:
    snapshot_id: str
    provider_id: str
    provider_fixture_id: str
    fixture: CanonicalFixtureIdentity
    observed_at: datetime
    event_time: datetime
    state: EventState
    home_score: int
    away_score: int
    statistics: tuple[StatisticValue, ...]
    available_markets: tuple[MarketIdentity, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.snapshot_id, "snapshot_id"),
            (self.provider_id, "provider_id"),
            (self.provider_fixture_id, "provider_fixture_id"),
        ):
            _nonempty(value, name)
        _aware(self.observed_at, "observed_at")
        _aware(self.event_time, "event_time")
        if self.event_time > self.observed_at:
            raise ValueError("event_time may not be after observed_at")
        _int(self.home_score, "home_score")
        _int(self.away_score, "away_score")
        if len({item.metric_id for item in self.statistics}) != len(self.statistics):
            raise ValueError("statistics may not contain duplicate metric_id")
        if len({item.key for item in self.available_markets}) != len(self.available_markets):
            raise ValueError("available_markets may not contain duplicate market identity")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ReconciliationPolicy:
    max_snapshot_age_seconds: int
    max_observation_skew_seconds: int
    max_kickoff_delta_seconds: int
    required_stat_metrics: tuple[str, ...]
    max_stat_absolute_delta: int
    required_market_keys: tuple[str, ...] = ()
    allow_state_lag_live_to_paused: bool = True

    def __post_init__(self) -> None:
        for value, name in (
            (self.max_snapshot_age_seconds, "max_snapshot_age_seconds"),
            (self.max_observation_skew_seconds, "max_observation_skew_seconds"),
            (self.max_kickoff_delta_seconds, "max_kickoff_delta_seconds"),
            (self.max_stat_absolute_delta, "max_stat_absolute_delta"),
        ):
            _int(value, name, minimum=0)
        if self.max_snapshot_age_seconds <= 0:
            raise ValueError("max_snapshot_age_seconds must be positive")
        if self.max_observation_skew_seconds <= 0:
            raise ValueError("max_observation_skew_seconds must be positive")
        if len(set(self.required_stat_metrics)) != len(self.required_stat_metrics):
            raise ValueError("required_stat_metrics may not contain duplicates")
        if len(set(self.required_market_keys)) != len(self.required_market_keys):
            raise ValueError("required_market_keys may not contain duplicates")


class ReconciliationStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ReconciliationAssessment:
    status: ReconciliationStatus
    reasons: tuple[str, ...]
    primary_fingerprint: str
    fallback_fingerprint: str
    compared_market_keys: tuple[str, ...]
    compared_stat_metrics: tuple[str, ...]
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_provider_switch:
            raise ValueError("reconciliation may not enable automatic provider switching")
        if self.automatic_wagering:
            raise ValueError("reconciliation may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def _terminal(state: EventState) -> bool:
    return state in {EventState.FINISHED, EventState.CANCELLED, EventState.POSTPONED}


def reconcile_snapshots(
    primary: ProviderEventSnapshot,
    fallback: ProviderEventSnapshot,
    policy: ReconciliationPolicy,
    *,
    now: datetime,
) -> ReconciliationAssessment:
    _aware(now, "now")
    block: list[str] = []
    watch: list[str] = []

    if primary.provider_id == fallback.provider_id:
        block.append("PROVIDERS_MUST_DIFFER")
    if primary.fixture.sport != fallback.fixture.sport:
        block.append("SPORT_MISMATCH")
    if primary.fixture.canonical_fixture_id != fallback.fixture.canonical_fixture_id:
        block.append("CANONICAL_FIXTURE_MISMATCH")
    if primary.fixture.competition_id != fallback.fixture.competition_id:
        block.append("COMPETITION_MISMATCH")
    if primary.fixture.home_entity_id != fallback.fixture.home_entity_id:
        block.append("HOME_ENTITY_MISMATCH")
    if primary.fixture.away_entity_id != fallback.fixture.away_entity_id:
        block.append("AWAY_ENTITY_MISMATCH")
    kickoff_delta = abs(int((primary.fixture.kickoff_utc - fallback.fixture.kickoff_utc).total_seconds()))
    if kickoff_delta > policy.max_kickoff_delta_seconds:
        block.append("KICKOFF_MISMATCH")
    elif kickoff_delta > 0:
        watch.append("KICKOFF_WITHIN_TOLERANCE")

    for label, snapshot in (("PRIMARY", primary), ("FALLBACK", fallback)):
        if snapshot.observed_at > now:
            block.append(f"{label}_SNAPSHOT_FROM_FUTURE")
        elif now - snapshot.observed_at > timedelta(seconds=policy.max_snapshot_age_seconds):
            block.append(f"{label}_SNAPSHOT_STALE")

    observation_skew = abs(int((primary.observed_at - fallback.observed_at).total_seconds()))
    if observation_skew > policy.max_observation_skew_seconds:
        block.append("OBSERVATION_SKEW_EXCEEDED")

    event_skew = abs(int((primary.event_time - fallback.event_time).total_seconds()))
    if event_skew > policy.max_observation_skew_seconds:
        block.append("EVENT_TIME_SKEW_EXCEEDED")

    if primary.state != fallback.state:
        allowed_lag = policy.allow_state_lag_live_to_paused and {primary.state, fallback.state} == {EventState.LIVE, EventState.PAUSED}
        if allowed_lag:
            watch.append("STATE_LAG_WITHIN_ALLOWED_TRANSITION")
        elif _terminal(primary.state) or _terminal(fallback.state):
            block.append("TERMINAL_EVENT_STATE_MISMATCH")
        else:
            block.append("EVENT_STATE_MISMATCH")

    if primary.home_score != fallback.home_score or primary.away_score != fallback.away_score:
        block.append("SCORE_MISMATCH")

    primary_stats = {item.metric_id: item for item in primary.statistics}
    fallback_stats = {item.metric_id: item for item in fallback.statistics}
    compared_stats: list[str] = []
    for metric_id in policy.required_stat_metrics:
        left = primary_stats.get(metric_id)
        right = fallback_stats.get(metric_id)
        if left is None or right is None:
            block.append(f"MISSING_REQUIRED_STAT:{metric_id}")
            continue
        compared_stats.append(metric_id)
        if abs(left.home_value - right.home_value) > policy.max_stat_absolute_delta or abs(left.away_value - right.away_value) > policy.max_stat_absolute_delta:
            block.append(f"STAT_DELTA_EXCEEDED:{metric_id}")
        elif left != right:
            watch.append(f"STAT_DELTA_WITHIN_TOLERANCE:{metric_id}")

    primary_markets = {item.key for item in primary.available_markets}
    fallback_markets = {item.key for item in fallback.available_markets}
    compared_market_keys = tuple(sorted(primary_markets & fallback_markets))
    for market_key in policy.required_market_keys:
        if market_key not in primary_markets:
            block.append(f"PRIMARY_MISSING_REQUIRED_MARKET:{market_key}")
        if market_key not in fallback_markets:
            block.append(f"FALLBACK_MISSING_REQUIRED_MARKET:{market_key}")

    # Provider prices are intentionally not compared for equality. Reconciliation
    # protects event/market identity; price disagreement may be legitimate market information.
    if block:
        status = ReconciliationStatus.BLOCK
        reasons = tuple(dict.fromkeys(block + watch))
    elif watch:
        status = ReconciliationStatus.WATCH
        reasons = tuple(dict.fromkeys(watch))
    else:
        status = ReconciliationStatus.PASS
        reasons = ()
    return ReconciliationAssessment(
        status=status,
        reasons=reasons,
        primary_fingerprint=primary.fingerprint,
        fallback_fingerprint=fallback.fingerprint,
        compared_market_keys=compared_market_keys,
        compared_stat_metrics=tuple(compared_stats),
    )
