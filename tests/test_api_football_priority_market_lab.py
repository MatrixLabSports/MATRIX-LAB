from tools.api_football_priority_market_lab import build, PRIORITY_MARKETS


def test_priority_labs_open_when_catalog_mapping_is_physically_observed():
    catalog={"matches":{
        "TEAM_TOTAL_GOALS_HOME":[{"id":1,"name":"Home Team Total Goals"}],
        "TEAM_TOTAL_GOALS_AWAY":[{"id":2,"name":"Away Team Total Goals"}],
        "DOUBLE_CHANCE_12":[{"id":3,"name":"Double Chance"}],
        "ASIAN_OR_EUROPEAN_HANDICAP":[{"id":4,"name":"Asian Handicap"}],
    }}
    r=build(catalog,target_date_bogota="2026-10-24")
    assert r["status"]=="PASS"
    assert r["active_price_coverage_labs"]==4
    assert r["blocked_price_labs"]==0
    assert {x["market_key"] for x in r["rows"]}==set(PRIORITY_MARKETS)
    assert all(x["lab_state"]=="LAB_PRICE_COVERAGE_ACTIVE" for x in r["rows"])


def test_priority_labs_never_invent_probability():
    r=build({"matches":{}},target_date_bogota="2026-10-24")
    assert r["active_price_coverage_labs"]==0
    assert all(x["p_matrix_status"]=="NOT_GENERATED" for x in r["rows"])
    assert all(x["p_sharp_status"]=="NOT_GENERATED" for x in r["rows"])
    assert r["odds_used_to_generate_p_matrix"] is False
    assert r["silent_probability_imputation"] is False
    assert r["automatic_wagering"] is False
    assert r["real_money"]=="BLOCKED"
