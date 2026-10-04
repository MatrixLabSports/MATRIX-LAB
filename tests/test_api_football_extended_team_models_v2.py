from tools.api_football_extended_team_models_v2 import _folds, _raw_features


def _row(i):
    return {
        "fixture_id":str(i),
        "expected_total":10.0+i*0.001,
        "expected_home":5.2,
        "expected_away":4.8,
        "home_for_mean":5.1,
        "home_against_mean":4.9,
        "away_for_mean":4.7,
        "away_against_mean":5.3,
        "league_id":"72" if i%2 else "252",
        "target_total":10.0,
    }


def test_internal_folds_are_expanding_and_disjoint():
    rows=[_row(i) for i in range(220)]
    folds=_folds(rows)
    assert len(folds)==3
    for train,test in folds:
        assert train
        assert test
        assert not ({r["fixture_id"] for r in train} & {r["fixture_id"] for r in test})
        assert train==rows[:len(train)]


def test_feature_modes_are_explicit():
    row=_row(1)
    assert len(_raw_features(row,"EXPECTED_ONLY"))==1
    assert len(_raw_features(row,"TEAM_STRENGTH"))==7
    assert len(_raw_features(row,"TEAM_STRENGTH_LEAGUE"))==9
