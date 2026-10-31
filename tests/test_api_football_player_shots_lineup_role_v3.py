from tools.api_football_player_shots_lineup_role_v3 import _roles, _roles_with_conflicts, _poisson_over

def test_lineup_roles_are_source_of_truth():
    payload={"response":[{"startXI":[{"player":{"id":1}}],"substitutes":[{"player":{"id":2}}]}]}
    assert _roles(payload)=={"1":"STARTER","2":"SUBSTITUTE"}

def test_player_shots_over_probability_monotonic():
    assert _poisson_over(3.0,1.5)>_poisson_over(2.0,1.5)>_poisson_over(1.0,1.5)

def test_ambiguous_lineup_role_is_quarantined():
    payload={"response":[{"startXI":[{"player":{"id":545246}}],"substitutes":[{"player":{"id":545246}}]}]}
    roles,conflicts=_roles_with_conflicts(payload)
    assert "545246" not in roles
    assert conflicts==["545246"]
