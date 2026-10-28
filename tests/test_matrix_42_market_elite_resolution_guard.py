from tools.matrix_42_market_elite_resolution_guard import load, validate

def test_resolution_matrix_is_complete():
    out=validate(load())
    assert out["status"]=="PASS"
    assert out["total_lanes"]==42
    assert out["owned_blockers"]==42

def test_no_live_tennis_lane_is_prematch_capable():
    data=load()
    for row in data["lanes"]:
        if row["elite_resolution_status"]=="LIVE_FEATURE_PATH_NOT_VALID_AS_PREMATCH_MODEL":
            assert row["prematch_model_capable_now"] is False

def test_only_current_governed_family_is_telegram_authorized():
    data=load()
    ready=[x["market_key"] for x in data["lanes"] if x["telegram_authorized_now"]]
    assert ready==["TOTAL_GOALS_OVER_UNDER"]
