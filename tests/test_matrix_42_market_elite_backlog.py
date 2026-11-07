from tools.matrix_42_market_elite_backlog import build

def test_backlog_has_all_42_and_owners():
    out=build()
    assert out["status"]=="PASS"
    assert out["total_lanes"]==42
    assert out["governance"]["all_unresolved_have_owner"] is True
    assert out["governance"]["all_unresolved_have_action"] is True

def test_backlog_preserves_temporal_integrity():
    out=build()
    assert out["governance"]["no_live_as_prematch"] is True
    assert out["governance"]["real_money"]=="BLOCKED"
