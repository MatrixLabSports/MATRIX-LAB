"""Prove Colombia quote collection cannot burn credits before 120m or send Telegram."""
import json
from datetime import datetime,timezone
from pathlib import Path
import pytest
from tools.matrix_colombia_239_safe_research_quote_adapter import check,adapt

ROOT=Path("evidence/football_world_inventory")
def files():
    return [
      json.loads((ROOT/"2026-11-24/MATRIX_COLOMBIA_BROWSER_THREE_SOURCE_DIRECT_OBSERVATIONS.json").read_bytes()),
      json.loads((ROOT/"2026-11-24/MATRIX_COLOMBIA_THREE_SOURCE_READINESS_RUN_45090559298.json").read_bytes()),
      json.loads((ROOT/"2026-11-22/MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json").read_bytes())
    ]
class NoNetwork:
    def get(self,*args,**kwargs):
        raise AssertionError("OUTSIDE_WINDOW_MUST_NOT_TOUCH_QUOTE_PROVIDER")
def test_real_two_verified_colombia_matches_as_research_only_odds_intake():
    a,b=adapt(*files())
    assert len(a["fixtures"])==2
    assert [x["source_fixture_id"] for x in a["fixtures"]]==["401934688","401934706"]
    assert a["signal_generation_authorized"] is False
    assert b["market_signal_authorized"] is False
def test_now_not_in_120m_window_no_api_call_even_with_key():
    result=check(*files(),key="fake-test-key",session=NoNetwork(),
       now=datetime(2026,11,23,1,0,tzinfo=timezone.utc))
    assert result["in_120m_window"]==0
    assert result["network_calls"]==0
    assert result["status"]=="WAITING_FOR_GOVERNED_PREMATCH_WINDOW"
    assert result["telegram_messages_sent"]==0
def test_inside_120m_without_key_stays_blocked():
    result=check(*files(),key="",session=NoNetwork(),
       now=datetime(2026,11,24,22,0,tzinfo=timezone.utc))
    assert result["in_120m_window"]==1
    assert result["quota_status"]=="MISSING_ODDS_API_NET_KEY"
    assert result["network_calls"]==0
    assert result["signal_generation_authorized"] is False
def test_global_quota_guard_failure_must_not_call_provider():
    result=check(*files(),key="test",session=NoNetwork(),
       now=datetime(2026,11,24,22,0,tzinfo=timezone.utc),
       global_quota_guard={"schema":"BLOCKED_MISSING_GLOBAL_QUOTA_GUARD"})
    assert result["network_calls"]==0
    assert result["quota_status"]=="BLOCKED_GLOBAL_QUOTA_EXHAUSTED_OR_UNVERIFIED"
def test_research_probability_promotion_forbidden():
    a=files();a[2]["research_scores"][0]["production_p_matrix_authorized"]=True
    with pytest.raises(ValueError,match="CROSS_SOURCE_RESEARCH_SCORE_CONTRADICTION"):
        adapt(*a)
def test_wrong_triple_source_research_id_fails_closed():
    a=files();a[1]["three_source_matches"][0]["espn_event_id"]="999999"
    with pytest.raises(ValueError,match="MISSING_VERIFIED_SOURCE_IDENTITY_OR_RESEARCH_SCORE"):
        adapt(*a)
