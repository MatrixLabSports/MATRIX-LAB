from tools.cor0203_r706_target_history_audit import audit_player


def test_audit_requires_every_model_history_component():
    state={
        "history":{
            "matches":{"P":[1,0,1]},
            "overall":{"P":[2,3]},
            "surface":{"P":{"Hard":[1,2]}},
            "serve":{"P":[30,50]},
            "ret":{"P":[20,50]},
            "opp_strength":{"P":[1.5,3]},
        },
        "elo_overall":{"P":1510},
        "elo_surface":{"Hard":{"P":1505}},
        "glicko_overall":{"P":{"r":1510,"rd":200}},
        "glicko_surface":{"Hard":{"P":{"r":1505,"rd":210}}},
    }
    row=audit_player(state,"P")
    assert row["fully_history_ready"] is True
    del state["history"]["serve"]["P"]
    row=audit_player(state,"P")
    assert row["fully_history_ready"] is False
    assert row["required_components"]["serve_history"] is False
