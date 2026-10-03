from tools.cor0203_rapidapi_stats_rich_history_probe import _eligible, _stat_summary


def test_eligible_requires_strict_pre_cut_and_nonterminal():
    row={
        "date":"2026-09-20T12:00:00Z",
        "result_type":"completed",
        "tournament":{"rankId":1,"court":{"name":"Hard"}},
    }
    assert _eligible(row) is True
    row2=dict(row); row2["date"]="2026-09-21T00:00:00Z"
    assert _eligible(row2) is False
    row3=dict(row); row3["result_type"]="retired"
    assert _eligible(row3) is False


def test_stat_summary_keeps_model_required_service_counts():
    payload={"data":{
        "player1Stats":{"player1Id":1,"firstServeOf":70,"winningOnFirstServe":30,"winningOnFirstServeOf":40,"winningOnSecondServe":15,"winningOnSecondServeOf":30},
        "player2Stats":{"player2Id":2,"firstServeOf":65,"winningOnFirstServe":28,"winningOnFirstServeOf":39,"winningOnSecondServe":14,"winningOnSecondServeOf":26},
    }}
    out=_stat_summary(payload)
    assert out["player1Stats"]["firstServeOf"]==70
    assert out["player1Stats"]["winningOnFirstServe"]==30
    assert out["player1Stats"]["winningOnSecondServe"]==15
