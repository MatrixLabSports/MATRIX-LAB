from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence


@dataclass(frozen=True)
class TemporalObservation:
    decision_at: datetime
    target_available_at: datetime

    def __post_init__(self) -> None:
        for name in ("decision_at", "target_available_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name.upper()}_MUST_BE_AWARE")
        if self.target_available_at < self.decision_at:
            raise ValueError("TARGET_AVAILABLE_BEFORE_DECISION")


@dataclass(frozen=True)
class PurgedTemporalFold:
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    validation_start: datetime
    purge_cutoff: datetime


def purged_expanding_walk_forward(
    observations: Sequence[TemporalObservation],
    *,
    min_train: int,
    validation_size: int,
    embargo: timedelta = timedelta(0),
) -> tuple[PurgedTemporalFold, ...]:
    if min_train < 1 or validation_size < 1 or min_train + validation_size > len(observations):
        raise ValueError("INVALID_FOLD_CONFIGURATION")
    if embargo < timedelta(0):
        raise ValueError("EMBARGO_MUST_BE_NONNEGATIVE")
    for i, obs in enumerate(observations):
        if i and obs.decision_at < observations[i - 1].decision_at:
            raise ValueError("OBSERVATIONS_NOT_SORTED")

    folds: list[PurgedTemporalFold] = []
    start = min_train
    while start + validation_size <= len(observations):
        validation = tuple(range(start, start + validation_size))
        validation_start = observations[start].decision_at
        purge_cutoff = validation_start - embargo
        train = tuple(
            i for i in range(start)
            if observations[i].target_available_at <= purge_cutoff
        )
        if len(train) < min_train:
            # A configured fold is not admissible if unresolved/purged labels reduce
            # the actual training set below the declared minimum.
            start += validation_size
            continue
        folds.append(PurgedTemporalFold(train, validation, validation_start, purge_cutoff))
        start += validation_size
    if not folds:
        raise ValueError("NO_ADMISSIBLE_PURGED_FOLDS")
    return tuple(folds)


def final_chronological_holdout_indices(n: int, *, holdout_size: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if type(n) is not int or type(holdout_size) is not int or n < 2 or holdout_size < 1 or holdout_size >= n:
        raise ValueError("FINAL_HOLDOUT_CONFIGURATION_INVALID")
    split = n - holdout_size
    return tuple(range(split)), tuple(range(split, n))


def assert_no_tuning_on_holdout(*, tuning_indices: Sequence[int], holdout_indices: Sequence[int]) -> None:
    overlap = set(tuning_indices) & set(holdout_indices)
    if overlap:
        raise ValueError("FINAL_HOLDOUT_TOUCHED_BY_TUNING")
