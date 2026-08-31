from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

@dataclass(frozen=True)
class TemporalFold:
    train_indices: tuple[int,...]
    validation_indices: tuple[int,...]


def expanding_walk_forward(timestamps: Sequence[datetime], *, min_train: int, validation_size: int) -> tuple[TemporalFold,...]:
    n=len(timestamps)
    if min_train < 1 or validation_size < 1 or min_train+validation_size > n:
        raise ValueError("INVALID_FOLD_CONFIGURATION")
    for i,t in enumerate(timestamps):
        if t.tzinfo is None or t.utcoffset() is None:
            raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        if i and timestamps[i] < timestamps[i-1]:
            raise ValueError("TIMESTAMPS_NOT_SORTED")
    folds=[]
    stop=min_train
    while stop+validation_size <= n:
        folds.append(TemporalFold(tuple(range(stop)), tuple(range(stop,stop+validation_size))))
        stop += validation_size
    return tuple(folds)


def assert_final_holdout_untouched(*, tuning_indices: Sequence[int], holdout_indices: Sequence[int]) -> None:
    if set(tuning_indices) & set(holdout_indices):
        raise ValueError("FINAL_HOLDOUT_REUSE_FORBIDDEN")
