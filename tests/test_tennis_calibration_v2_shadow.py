from copy import deepcopy

import pytest

from tools.tennis_calibration_v2_shadow import build_shadow


FEATURES = [
    "rank_diff","rank_points_diff","age_diff","hand_same","form5_diff","form10_diff",
    "form20_diff","surface_wr_diff","overall_wr_diff","serve_pts_won_diff",
    "return_pts_won_diff","prior_opponent_strength_diff","elo_overall_diff","elo_surface_diff"
]


def _bundle():
    return {
        "candidate_id":"TENNIS_BASE12_ELO_REG_C0P01_20261001",
        "model":{
            "features":FEATURES,
            "scaler_mean":[0.0]*len(FEATURES),
            "scaler_scale":[1.0]*len(FEATURES),
            "coef":[0.01]*len(FEATURES),
            "intercept":0.0,
        },
        "inference_contract":{"candidate_future_cutoff_utc":"2026-10-02T00:00:00+00:00"},
    }


def _batch():
    base = {
        "rank_diff":10.0,"rank_points_diff":20.0,"age_diff":1.0,"hand_same":1.0,
        "form5_diff":0.2,"form10_diff":0.1,"form20_diff":0.05,"surface_wr_diff":0.1,
        "overall_wr_diff":0.1,"serve_pts_won_diff":0.02,"return_pts_won_diff":0.01,
        "prior_opponent_strength_diff":0.03,
    }
    obs = {
        "event_id":"future-1","canonical_source_event_id":"provider-1","observation_index":103,
        "observation_sha256":"a"*64,"freeze_at_utc":"2026-10-02T00:10:00+00:00",
        "event_start_utc":"2026-10-02T02:00:00+00:00","alphabetical_player_a":"A",
        "alphabetical_player_b":"B","surface":"Hard","features":base,
        "elo":{"elo_overall_diff":50.0,"elo_surface_diff":40.0},"outcome":None,
    }
    return {
        "holdout_id":"A22_POST_AUDIT_VIRGIN_HOLDOUT_V1",
        "metrics":"SEALED_UNTIL_600","outcomes_read":0,"batch_sha256":"b"*64,
        "created_at_utc":"2026-10-02T00:10:00+00:00","observations":[obs],
    }


def test_future_only_shadow_scoring_preserves_seal():
    d=build_shadow(_bundle(),_batch())
    assert d["row_count"]==1
    assert d["outcomes_read"]==0
    assert d["metrics_opened"] is False
    assert d["real_money"]=="BLOCKED"
    assert 0.0 < d["rows"][0]["p_player_a"] < 1.0
    assert d["rows"][0]["outcome"] is None


def test_rejects_pre_candidate_freeze():
    b=_batch()
    b["observations"][0]["freeze_at_utc"]="2026-10-01T23:59:59+00:00"
    with pytest.raises(ValueError,match="CANDIDATE_PRE_FREEZE_EVENT_FORBIDDEN"):
        build_shadow(_bundle(),b)


def test_rejects_missing_observed_feature_instead_of_imputing():
    b=_batch()
    del b["observations"][0]["features"]["form5_diff"]
    with pytest.raises(ValueError,match="OBSERVED_FEATURE_MISSING:form5_diff"):
        build_shadow(_bundle(),b)


def test_rejects_outcome_visibility():
    b=_batch()
    b["observations"][0]["outcome"]=1
    with pytest.raises(ValueError,match="OUTCOME_PRESENT_AT_SHADOW_FREEZE"):
        build_shadow(_bundle(),b)


def test_rejects_post_start_freeze():
    b=_batch()
    b["observations"][0]["freeze_at_utc"]="2026-10-02T03:00:00+00:00"
    with pytest.raises(ValueError,match="POST_START_SHADOW_FREEZE_FORBIDDEN"):
        build_shadow(_bundle(),b)
