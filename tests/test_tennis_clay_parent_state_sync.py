import pytest

from tools.tennis_clay_parent_state_sync import sync


def parent():
    return {
        "lane_id":"ATP_CHALLENGER_MEN_SINGLES_CLAY",
        "holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1",
        "holdout_status":"ACTIVE_ZERO_OBSERVATIONS",
        "prospective_observations":0,
        "metrics_opened":False,
        "real_money":"BLOCKED",
        "status":"ACTIVE_PROSPECTIVE_RESEARCH",
        "sha256_without_self":"old",
    }


def prospective(count=2):
    return {
        "lane_id":"ATP_CHALLENGER_MEN_SINGLES_CLAY",
        "holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1",
        "observation_count":count,
        "unique_physical_event_count":count,
        "metrics_opened":False,
        "outcomes_read":0,
        "real_money":"BLOCKED",
        "status":"ACTIVE_PROSPECTIVE",
    }


def test_sync_updates_zero_to_two():
    out=sync(parent(),prospective(2))
    assert out["prospective_observations"]==2
    assert out["prospective_unique_physical_event_count"]==2
    assert out["holdout_status"]=="ACTIVE_PROSPECTIVE"
    assert out["metrics_opened"] is False
    assert out["real_money"]=="BLOCKED"
    assert len(out["sha256_without_self"])==64


def test_zero_stays_zero():
    out=sync(parent(),prospective(0))
    assert out["prospective_observations"]==0
    assert out["holdout_status"]=="ACTIVE_ZERO_OBSERVATIONS"


def test_rejects_open_metrics():
    p=prospective(2)
    p["metrics_opened"]=True
    with pytest.raises(ValueError,match="PROSPECTIVE_METRICS_OPENED"):
        sync(parent(),p)


def test_rejects_lane_mismatch():
    p=prospective(2)
    p["lane_id"]="WRONG"
    with pytest.raises(ValueError,match="LANE_ID_MISMATCH"):
        sync(parent(),p)
