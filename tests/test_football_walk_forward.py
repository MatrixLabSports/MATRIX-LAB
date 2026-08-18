from datetime import datetime, timedelta, timezone

import pytest

from app.research.football.dataset import FootballResearchRow
from app.research.football.walk_forward import WalkForwardPolicy, build_walk_forward_folds


def row(i, *, label_delay_hours=6):
    t = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return FootballResearchRow(
        fixture_id=str(i),
        as_of_utc=t.isoformat(),
        partition="train",
        features={"competition": "Liga", "x": i},
        labels={"over_2_5": i % 2 == 0},
        label_observed_at_utc=(t + timedelta(hours=label_delay_hours)).isoformat(),
    )


def test_walk_forward_generates_non_overlapping_embargoed_folds():
    folds = build_walk_forward_folds(
        [row(i) for i in range(220)],
        policy=WalkForwardPolicy(
            initial_train_days=90,
            test_days=30,
            step_days=30,
            embargo_hours=24,
            min_train_fixtures=50,
            min_test_fixtures=20,
        ),
    )
    assert len(folds) >= 3
    for fold in folds:
        assert not (set(fold.train_fixture_ids) & set(fold.test_fixture_ids))
        assert datetime.fromisoformat(fold.train_end_utc) < datetime.fromisoformat(fold.test_start_utc)


def test_walk_forward_excludes_training_fixture_whose_label_is_not_known_by_train_end():
    rows = [row(i) for i in range(120)]
    delayed = row(80, label_delay_hours=24 * 30)
    rows[80] = delayed
    folds = build_walk_forward_folds(
        rows,
        policy=WalkForwardPolicy(
            initial_train_days=90,
            test_days=20,
            step_days=20,
            embargo_hours=1,
            min_train_fixtures=1,
            min_test_fixtures=1,
        ),
    )
    first = folds[0]
    assert "80" not in first.train_fixture_ids


def test_walk_forward_supports_rolling_train_window():
    folds = build_walk_forward_folds(
        [row(i) for i in range(180)],
        policy=WalkForwardPolicy(
            initial_train_days=60,
            test_days=20,
            step_days=20,
            embargo_hours=0,
            min_train_fixtures=20,
            min_test_fixtures=10,
            expanding_train=False,
        ),
    )
    assert folds
    assert folds[1].train_start_utc > folds[0].train_start_utc


def test_walk_forward_rejects_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        build_walk_forward_folds([], policy=WalkForwardPolicy(min_train_fixtures=0, min_test_fixtures=0))
