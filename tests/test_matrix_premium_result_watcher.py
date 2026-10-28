from tools.matrix_premium_result_watcher import _supported_result

def record(market="Más de 2.5 goles"):
    return {"market":market,"odds":1.80}

def test_over25_result_win_and_loss():
    assert _supported_result(record(),{"home_goals":2,"away_goals":1,"status":"FT"})["won"] is True
    assert _supported_result(record(),{"home_goals":1,"away_goals":1,"status":"FT"})["won"] is False

def test_unknown_market_fails_closed():
    assert _supported_result(record("Ambos marcan"),{"home_goals":2,"away_goals":1,"status":"FT"}) is None
