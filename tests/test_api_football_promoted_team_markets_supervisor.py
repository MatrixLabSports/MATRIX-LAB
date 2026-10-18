from tools.api_football_promoted_team_markets_supervisor import _canonical_offer, _poisson_over, _nb_over

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
