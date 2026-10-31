from tools.matrix_multi_market_supervisor import build

def _by_key(rows):
    return {x["market_key"]:x for x in rows}

def test_supervisor_distinguishes_real_prematch_capability():
    out=build()
    by=_by_key(out["rows"])
    assert by["TOTAL_GOALS_OVER_UNDER"]["prematch_model_capable"] is True
    assert by["PLAYER_SHOTS"]["prematch_model_capable"] is True
    assert by["CORNERS_OVER_UNDER"]["prematch_model_capable"] is False
    assert "COVERAGE_ONLY" in by["CORNERS_OVER_UNDER"]["capability_mode"]
    assert by["SET_WINNER"]["prematch_model_capable"] is False
    assert by["SET_WINNER"]["capability_mode"]=="LIVE_ONLY_NOT_PREMATCH"
    assert by["ACES"]["prematch_model_capable"] is False
    assert by["ACES"]["capability_mode"]=="SOURCE_LAB_ONLY_PREMATCH_MODEL_REQUIRED"

def test_live_and_coverage_paths_cannot_be_production_authorized():
    out=build()
    for row in out["rows"]:
        if row["capability_mode"]=="LIVE_ONLY_NOT_PREMATCH" or "COVERAGE_ONLY" in row["capability_mode"] or row["capability_mode"]=="SOURCE_LAB_ONLY_PREMATCH_MODEL_REQUIRED":
            assert row["production_authorized"] is False

def test_core_invariants_remain():
    out=build()
    assert out["total_required_lanes"]==42
    assert out["invariants"]["live_only_never_counts_as_prematch"] is True
    assert out["invariants"]["coverage_only_never_counts_as_prematch"] is True
    assert out["invariants"]["real_money"]=="BLOCKED"
