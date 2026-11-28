import json
from pathlib import Path
from tools.api_football_player_shots_v3_lineup_role import _roles_from_lineup, _poisson_over

def test_lineup_roles_are_authoritative():
    p={"response":[{"startXI":[{"player":{"id":1}},{"player":{"id":2}}],
                    "substitutes":[{"player":{"id":3}}]}]}
    assert _roles_from_lineup(p)=={"1":"STARTER","2":"STARTER","3":"SUBSTITUTE"}

def test_role_conflict_fails():
    p={"response":[{"startXI":[{"player":{"id":1}}],
                    "substitutes":[{"player":{"id":1}}]}]}
    try:
        _roles_from_lineup(p)
    except ValueError as exc:
        assert "LINEUP_ROLE_CONFLICT" in str(exc)
    else:
        raise AssertionError("conflicting role must fail")

def test_probability_monotonicity():
    assert _poisson_over(2.5,0.5)>_poisson_over(2.5,1.5)>_poisson_over(2.5,2.5)

def test_source_code_forbids_games_substitute_as_feature():
    src=Path("tools/api_football_player_shots_v3_lineup_role.py").read_text(encoding="utf-8")
    assert '"games_substitute_used":False' in src
    assert '"historical_role_label_source":"/fixtures/lineups"' in src
    assert 'games.get("substitute")' not in src
