from tools.api_football_match_total_shots_settlement import calibration_metrics, build_state


def row(fid:int,p:float,y:bool,odds:float=2.0)->dict:
    return {
        "fixture_id":str(fid),
        "frozen_probability_over":p,
        "outcome_over":y,
        "over_odds":odds,
    }


def test_gate_30_stays_sealed_until_30_finals():
    freezes=[{"fixture_id":str(i)} for i in range(30)]
    settlements=[row(i,0.60,i%2==0) for i in range(29)]
    state=build_state(freezes,settlements,{})
    assert state["gate_30"]["metrics_opened"] is False
    assert state["gate_30"]["status"]=="SEALED_AWAIT_FINALS"
    assert state["gate_30"]["remaining_finals"]==1
    assert state["real_money"]=="BLOCKED"


def test_gate_30_opens_exactly_at_30_without_promotion():
    freezes=[{"fixture_id":str(i)} for i in range(30)]
    settlements=[row(i,0.60,i%2==0) for i in range(30)]
    state=build_state(freezes,settlements,{})
    gate=state["gate_30"]
    assert gate["metrics_opened"] is True
    assert gate["observations_used"]==30
    assert gate["metrics"]["sample_size"]==30
    assert state["parameter_tuning_allowed"] is False
    assert state["model_promotion_performed"] is False
    assert state["telegram_signal_authorized"] is False
    assert state["paper_bankroll_authorized"] is False
    assert state["real_money"]=="BLOCKED"


def test_calibration_metrics_include_required_outputs_and_shadow_roi():
    rows=[
        row(1,0.80,True,1.80),
        row(2,0.70,False,2.00),
        row(3,0.40,False,1.90),
        row(4,0.30,True,2.50),
    ]
    m=calibration_metrics(rows)
    assert m["sample_size"]==4
    assert 0 <= m["brier_score"] <= 1
    assert m["log_loss"] > 0
    assert 0 <= m["ece_5bin"] <= 1
    assert 0 <= m["max_calibration_error_5bin"] <= 1
    assert "shadow_policy" in m
    assert m["shadow_policy"]["bet_count"] >= 1
