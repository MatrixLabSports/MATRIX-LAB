from tools.api_football_btts_challenger_v3 import (
    _features,
    _temporal_folds,
)


def _row(i):
    return {
        "fixture_id":str(i),
        "kickoff_utc":f"2026-01-{(i%28)+1:02d}T00:00:00+00:00",
        "poisson":{"btts":0.55},
        "baseline":{"btts":0.50},
        "expected_home_goals":1.4,
        "expected_away_goals":1.1,
        "home_history_count":10,
        "away_history_count":10,
        "outcome":{"btts":bool(i%2)},
    }


def test_feature_modes_are_finite_and_nonempty():
    row=_row(1)
    for mode in ("BETA_POISSON","POISSON_BASELINE_BLEND","RICH_LOGISTIC"):
        values=_features(row,mode)
        assert values
        assert all(isinstance(v,float) for v in values)


def test_temporal_folds_never_train_on_their_validation_rows():
    rows=[_row(i) for i in range(1300)]
    folds=_temporal_folds(rows)
    assert len(folds)==3
    prior_end=1200
    for train,test in folds:
        assert len(train)==prior_end
        assert train==rows[:prior_end]
        assert test==rows[prior_end:prior_end+len(test)]
        assert not ({r["fixture_id"] for r in train} & {r["fixture_id"] for r in test})
        prior_end+=len(test)
    assert prior_end==len(rows)
