from collections import defaultdict
from tools.api_football_extended_team_pit_dataset import _history_values, _mean

def test_history_values_use_only_existing_prior_state():
    history=[
        {"own":{"CORNERS":2.0},"allowed":{"CORNERS":5.0}},
        {"own":{"CORNERS":4.0},"allowed":{"CORNERS":3.0}},
    ]
    own,allowed=_history_values(history,"CORNERS")
    assert own==[2.0,4.0]
    assert allowed==[5.0,3.0]
    assert _mean(own)==3.0
    assert _mean(allowed)==4.0

def test_missing_metric_is_not_silently_imputed():
    history=[
        {"own":{"CORNERS":2.0},"allowed":{"CORNERS":None}},
        {"own":{"CORNERS":None},"allowed":{"CORNERS":3.0}},
    ]
    own,allowed=_history_values(history,"CORNERS")
    assert own==[2.0]
    assert allowed==[3.0]
