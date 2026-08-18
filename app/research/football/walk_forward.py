from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.research.football.dataset import FootballResearchRow


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class WalkForwardPolicy:
    initial_train_days: int = 365
    test_days: int = 30
    step_days: int = 30
    embargo_hours: int = 24
    min_train_fixtures: int = 500
    min_test_fixtures: int = 100
    expanding_train: bool = True

    def __post_init__(self) -> None:
        for name in ("initial_train_days", "test_days", "step_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("embargo_hours", "min_train_fixtures", "min_test_fixtures"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_start_utc: str
    train_end_utc: str
    test_start_utc: str
    test_end_utc: str
    train_fixture_ids: tuple[str, ...]
    test_fixture_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        train_start = _aware(self.train_start_utc)
        train_end = _aware(self.train_end_utc)
        test_start = _aware(self.test_start_utc)
        test_end = _aware(self.test_end_utc)
        if train_start > train_end or test_start > test_end:
            raise ValueError("invalid fold time interval")
        if train_end > test_start:
            raise ValueError("train and test windows must not overlap")
        if set(self.train_fixture_ids) & set(self.test_fixture_ids):
            raise ValueError("fixture leakage across train/test in fold")


@dataclass(frozen=True)
class _FixtureCutoff:
    fixture_id: str
    as_of: datetime
    label_at: datetime


def _fixture_cutoffs(rows: Iterable[FootballResearchRow]) -> list[_FixtureCutoff]:
    by_fixture: dict[str, list[FootballResearchRow]] = {}
    for row in rows:
        by_fixture.setdefault(row.fixture_id, []).append(row)
    result: list[_FixtureCutoff] = []
    for fixture_id, items in by_fixture.items():
        # The fixture's first information cutoff determines temporal membership.
        as_of = min(_aware(item.as_of_utc) for item in items)
        # Training may use the fixture only after every label needed by its observations
        # is known. This is deliberately conservative.
        label_at = max(_aware(item.label_observed_at_utc) for item in items)
        result.append(_FixtureCutoff(fixture_id=fixture_id, as_of=as_of, label_at=label_at))
    return sorted(result, key=lambda item: (item.as_of, item.fixture_id))


def build_walk_forward_folds(
    rows: Iterable[FootballResearchRow],
    *,
    policy: WalkForwardPolicy = WalkForwardPolicy(),
) -> list[WalkForwardFold]:
    fixtures = _fixture_cutoffs(rows)
    if not fixtures:
        raise ValueError("walk-forward requires at least one fixture")

    first_time = fixtures[0].as_of
    last_time = fixtures[-1].as_of
    initial_delta = timedelta(days=policy.initial_train_days)
    test_delta = timedelta(days=policy.test_days)
    step_delta = timedelta(days=policy.step_days)
    embargo = timedelta(hours=policy.embargo_hours)

    train_end = first_time + initial_delta
    folds: list[WalkForwardFold] = []
    fold_index = 0
    while True:
        test_start = train_end + embargo
        test_end = test_start + test_delta
        if test_start > last_time:
            break

        if policy.expanding_train:
            train_start = first_time
        else:
            train_start = train_end - initial_delta

        train_ids = tuple(
            item.fixture_id
            for item in fixtures
            if train_start <= item.as_of < train_end and item.label_at <= train_end
        )
        test_ids = tuple(
            item.fixture_id
            for item in fixtures
            if test_start <= item.as_of < test_end
        )

        if len(train_ids) >= policy.min_train_fixtures and len(test_ids) >= policy.min_test_fixtures:
            folds.append(
                WalkForwardFold(
                    index=fold_index,
                    train_start_utc=train_start.isoformat(),
                    train_end_utc=train_end.isoformat(),
                    test_start_utc=test_start.isoformat(),
                    test_end_utc=test_end.isoformat(),
                    train_fixture_ids=train_ids,
                    test_fixture_ids=test_ids,
                )
            )
            fold_index += 1

        train_end += step_delta
        if test_end > last_time + test_delta:
            break

    return folds
