from tools.api_football_failed_team_markets_v3 import _nb_over, build_lane
from pathlib import Path
import json

def test_negative_binomial_over_is_monotonic_in_line():
    assert _nb_over(10.0,5.0,7.5)>_nb_over(10.0,5.0,9.5)>_nb_over(10.0,5.0,11.5)

def test_real_lane_keeps_final_validation_out_of_selection():
    p=Path("evidence/api_football/market_expansion/team_pit/corners_pit.jsonl")
    r=build_lane("CORNERS",p)
    assert r["internal_selection"]["final_validation_used_for_selection"] is False
    assert r["validation_used_for_parameter_tuning"] is False
    assert r["odds_used_to_generate_probability"] is False
    assert r["real_money"]=="BLOCKED"
    assert r["train_count"]>=200
    assert r["validation_count"]>=50
