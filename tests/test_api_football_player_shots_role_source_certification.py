from tools.api_football_player_shots_role_source_certification import _lineup_roles

def test_lineup_role_mapping_is_explicit():
    payload={"response":[
        {"startXI":[{"player":{"id":1,"name":"A"}},{"player":{"id":2,"name":"B"}}],
         "substitutes":[{"player":{"id":3,"name":"C"}}]}
    ]}
    roles=_lineup_roles(payload)
    assert roles=={"1":"STARTER","2":"STARTER","3":"SUBSTITUTE"}

def test_lineup_role_conflict_is_rejected():
    payload={"response":[
        {"startXI":[{"player":{"id":1}}],
         "substitutes":[{"player":{"id":1}}]}
    ]}
    try:
        _lineup_roles(payload)
    except ValueError as exc:
        assert "LINEUP_PLAYER_ROLE_CONFLICT" in str(exc)
    else:
        raise AssertionError("role conflict must fail")
