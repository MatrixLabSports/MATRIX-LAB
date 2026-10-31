from datetime import datetime, timedelta, timezone
import pytest
from tools.matrix_42_lane_freeze_producer import build_freeze

def test_all_42_accept_strict_prematch_freeze():
    from app.market.matrix_market_portfolio import ALL_MARKETS
    start=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    for market in ALL_MARKETS:
        row=build_freeze(market_lane=market.key,event_id="X-"+market.key,event_start_utc=start,
                         feature_snapshot={"source_valid":True,"lane":market.key},
                         source_artifacts=["evidence/test/source.json"])
        assert row["market_lane"]==market.key
        assert row["odds_used_to_generate_probability"] is False
        assert row["real_money"]=="BLOCKED"

def test_rejects_post_start():
    now=datetime.now(timezone.utc)
    with pytest.raises(ValueError,match="FREEZE_NOT_BEFORE_EVENT_START"):
        build_freeze(market_lane="ACES",event_id="1",event_start_utc=(now-timedelta(minutes=1)).isoformat(),
                     generated_at_utc=now.isoformat(),feature_snapshot={"x":1},source_artifacts=["x"])
