from tools.api_football_team_total_shots_side_models import _side_keys, _poisson_over, build_side

def _rows():
    rows=[]
    for i in range(274):
        split="TRAIN" if i<224 else "VALIDATION"
        eh=10.0+(i%7)*0.7
        ea=9.0+(i%5)*0.6
        th=round(eh + (1 if i%3==0 else -1 if i%5==0 else 0))
        ta=round(ea + (1 if i%4==0 else -1 if i%6==0 else 0))
        rows.append({
            "fixture_id":str(i),"kickoff_utc":f"2026-01-{(i%28)+1:02d}T00:00:00+00:00",
            "split":split,"league_id":"72",
            "expected_home":eh,"expected_away":ea,"expected_total":eh+ea,
            "home_for_mean":eh+0.5,"home_against_mean":ea+0.2,
            "away_for_mean":ea+0.4,"away_against_mean":eh+0.3,
            "home_history_count":20,"away_history_count":20,
            "target_home":th,"target_away":ta,"target_total":th+ta,
        })
    return rows

def test_side_market_bindings_are_not_combined():
    h=build_side("HOME",_rows())
    a=build_side("AWAY",_rows())
    assert h["market_binding"]["api_football_bet_id"]==221
    assert a["market_binding"]["api_football_bet_id"]==220
    assert h["lane"]=="TEAM_TOTAL_SHOTS_HOME"
    assert a["lane"]=="TEAM_TOTAL_SHOTS_AWAY"
    assert h["bookmaker_scope_alignment_certified"] is True
    assert a["bookmaker_scope_alignment_certified"] is True

def test_validation_is_not_used_for_selection():
    h=build_side("HOME",_rows())
    assert h["internal_selection"]["final_validation_used_for_selection"] is False
    assert h["validation_used_for_parameter_tuning"] is False
    assert h["odds_used_to_generate_probability"] is False
    assert h["real_money"]=="BLOCKED"

def test_poisson_probability_supports_bookmaker_half_lines():
    p11=_poisson_over(13.0,11.5)
    p13=_poisson_over(13.0,13.5)
    p15=_poisson_over(13.0,15.5)
    assert p11>p13>p15

def test_home_and_away_use_distinct_targets():
    assert _side_keys("HOME")["target"]=="target_home"
    assert _side_keys("AWAY")["target"]=="target_away"
