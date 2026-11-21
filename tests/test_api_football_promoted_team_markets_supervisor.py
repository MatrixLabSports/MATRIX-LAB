from tools.api_football_promoted_team_markets_supervisor import _canonical_offer, _poisson_over, _nb_over, MODEL_ONLY_RESEARCH_LANES, _load_json
from pathlib import Path

def test_canonical_offer_requires_over_under_pair():
    hits=[{
      "policy_reference_bookmaker":True,"bookmaker_name":"Betano","bet_id":221,
      "values":[
        {"value":"Over 12.5","odd":"1.90","main":True,"suspended":False},
        {"value":"Under 12.5","odd":"1.90","main":True,"suspended":False},
      ],
    }]
    x=_canonical_offer(hits,221)
    assert x is not None
    assert x["line"]==12.5
    assert x["bookmaker_name"]=="Betano"

def test_missing_pair_cannot_freeze():
    hits=[{"policy_reference_bookmaker":True,"bookmaker_name":"Betano","bet_id":221,"values":[{"value":"Over 12.5","odd":"1.90"}]}]
    assert _canonical_offer(hits,221) is None

def test_count_probabilities_are_line_monotonic():
    assert _poisson_over(13,10.5)>_poisson_over(13,13.5)>_poisson_over(13,16.5)
    assert _nb_over(28,10,25.5)>_nb_over(28,10,28.5)>_nb_over(28,10,31.5)


def test_team_total_shots_model_only_research_is_governed():
    assert MODEL_ONLY_RESEARCH_LANES=={"TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY"}
    home=_load_json(Path("evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json"))
    away=_load_json(Path("evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json"))
    assert home["prospective_eligible"] is True
    assert away["prospective_eligible"] is True
    assert home["historical_evaluation_line"]==15.5
    assert away["historical_evaluation_line"]==11.5
    assert home["odds_used_to_generate_probability"] is False
    assert away["odds_used_to_generate_probability"] is False
    assert home["real_money"]=="BLOCKED"
    assert away["real_money"]=="BLOCKED"
