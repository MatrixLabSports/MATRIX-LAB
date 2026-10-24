from tools.matrix_blocked_market_activation_plan import build

def test_activation_plan_prioritizes_price_ready_blocked_markets():
    supervisor={
        "generated_at_utc":"2026-10-24T11:00:00+00:00",
        "rows":[
            {"sport":"football","market_key":"TEAM_TOTAL_GOALS_HOME","display_name":"Home goals","operational_state":"BLOCKED_MODEL","price_state":"PRICE_FAMILY_OBSERVED","blockers":["BLOCKED_MODEL"]},
            {"sport":"football","market_key":"FIRST_HALF_TOTAL_GOALS_OVER_UNDER","display_name":"1H goals","operational_state":"BLOCKED_MODEL","price_state":"PRICE_FAMILY_NOT_OBSERVED","blockers":["BLOCKED_MODEL","BLOCKED_PRICE_FAMILY"]},
            {"sport":"tennis","market_key":"ACES","display_name":"Aces","operational_state":"BLOCKED_MODEL","price_state":"PRICE_MAPPING_REQUIRES_TENNIS_PROVIDER_OR_BOOK_CATALOG","blockers":["BLOCKED_MODEL","BLOCKED_TENNIS_STAT_MARKET_IMPLEMENTATION"]},
            {"sport":"football","market_key":"TOTAL_GOALS_OVER_UNDER","display_name":"Goals","operational_state":"ACTIVE","price_state":"PRICE_FAMILY_OBSERVED","blockers":[]},
        ],
    }
    r=build(supervisor)
    assert r["status"]=="PASS"
    assert r["blocked_model_count"]==3
    assert r["immediate_model_lab_candidates"]==["TEAM_TOTAL_GOALS_HOME"]
    assert r["rows"][0]["next_required_action"]=="BUILD_PROSPECTIVE_MODEL_LAB_NOW"
    assert r["policy"]["price_does_not_generate_p_matrix"] is True
    assert r["policy"]["real_money"]=="BLOCKED"


def test_workflow_allows_blocked_count_to_shrink():
    text=open(".github/workflows/matrix-multi-market-supervisor.yml",encoding="utf-8").read()
    assert 'assert j["blocked_model_count"]==13' not in text
    assert 'assert j["blocked_model_count"]==len(j["rows"])' in text
    assert '0 <= j["blocked_model_count"] <= 13' in text
