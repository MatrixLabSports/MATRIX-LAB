from tools.api_football_player_shots_v3_supervisor import _candidate_player, _parse_offers, _features, _poisson_over
from datetime import datetime, timezone

def test_unique_lineup_player_binding():
    lineup=[
      {"player_id":"10","player_name":"Juan Perez","role":"STARTER"},
      {"player_id":"11","player_name":"Pedro Ruiz","role":"SUBSTITUTE"},
    ]
    assert _candidate_player("Juan Perez Over 1.5",lineup)["player_id"]=="10"
    assert _candidate_player("Unknown Player Over 1.5",lineup) is None

def test_offer_requires_player_direction_line_and_two_sides():
    lineup=[{"player_id":"10","player_name":"Juan Perez","role":"STARTER"}]
    hits=[{
      "policy_reference_bookmaker":True,"bookmaker_name":"Betano","bet_id":240,"bet_name":"Home Player Shots",
      "values":[
        {"value":"Juan Perez Over 1.5","odd":"1.90","handicap":None,"main":True,"suspended":False},
        {"value":"Juan Perez Under 1.5","odd":"1.80","handicap":None,"main":True,"suspended":False},
      ]
    }]
    offers,blockers=_parse_offers(hits,lineup)
    assert len(offers)==1
    assert offers[0]["player_id"]=="10"
    assert offers[0]["line"]==1.5
    assert blockers==[]

def test_pit_features_require_history_and_same_role():
    kickoff=datetime(2026,10,1,tzinfo=timezone.utc)
    hist=[]
    for i in range(6):
        hist.append({
          "player_id":"10","kickoff_utc":f"2026-09-{20+i:02d}T10:00:00+00:00",
          "role":"STARTER","minutes":80,"shots":2+i%2
        })
    f=_features(hist,"10","STARTER",kickoff)
    assert f is not None
    assert f["prior_appearance_count"]==6
    assert f["prior_role_appearance_count"]==6
    assert f["role_expected_minutes"]==80

def test_probability_decreases_with_line():
    assert _poisson_over(2.5,1.5)>_poisson_over(2.5,2.5)
