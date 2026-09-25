import pytest

from tools.cor0203_batch_linkage_gate import validate_batch_linkage


HOLDOUT = "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
FREEZE = "2026-09-25T12:00:00+00:00"


def pre():
    return {
        "holdout_id": HOLDOUT,
        "created_before_feature_acquisition": True,
        "starting_observation_count": 8,
        "events": [
            {
                "event_id": "e9",
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            },
            {
                "event_id": "e10",
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            },
        ],
    }


def events():
    return {
        "holdout_id": HOLDOUT,
        "starting_observation_count": 8,
        "events": [
            {
                "event_id": "e9",
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": "2026-09-26T14:00:00+00:00",
                "players": [{"name": "Player A"}, {"name": "Player B"}],
            },
            {
                "event_id": "e10",
                "surface": "Hard",
                "tour_level": "ATP Challenger",
                "event_start_utc": "2026-09-26T16:00:00+00:00",
                "players": [{"name": "Player C"}, {"name": "Player D"}],
            },
        ],
    }


def test_multi_event_batch_passes():
    result = validate_batch_linkage(
        prefeature=pre(),
        events=events(),
        freeze_at_utc=FREEZE,
        expected_starting_count=8,
    )
    assert result["result"] == "PASS"
    assert result["batch_size"] == 2
    assert result["event_ids"] == ["e9", "e10"]


def test_placeholder_is_blocked():
    e = events()
    e["events"][0]["players"][1]["name"] = "QF1"
    with pytest.raises(ValueError, match="IDENTITY_NOT_FIXED"):
        validate_batch_linkage(
            prefeature=pre(), events=e, freeze_at_utc=FREEZE, expected_starting_count=8
        )


def test_post_start_freeze_is_blocked():
    with pytest.raises(ValueError, match="POST_START_FREEZE_FORBIDDEN"):
        validate_batch_linkage(
            prefeature=pre(),
            events=events(),
            freeze_at_utc="2026-09-26T17:00:00+00:00",
            expected_starting_count=8,
        )


def test_missing_prefeature_row_is_blocked():
    p = pre()
    p["events"] = [p["events"][0]]
    with pytest.raises(ValueError, match="MISSING_PRIOR_PREREGISTRATION"):
        validate_batch_linkage(
            prefeature=p, events=events(), freeze_at_utc=FREEZE, expected_starting_count=8
        )


def test_features_must_be_false_at_prefeature_stage():
    p = pre()
    p["events"][0]["features_loaded"] = True
    with pytest.raises(ValueError, match="PREFEATURE_FEATURES_ALREADY_LOADED"):
        validate_batch_linkage(
            prefeature=p, events=events(), freeze_at_utc=FREEZE, expected_starting_count=8
        )


def test_starting_count_cannot_drift():
    e = events()
    e["starting_observation_count"] = 7
    with pytest.raises(ValueError, match="EVENT_BATCH_START_COUNT_MISMATCH"):
        validate_batch_linkage(
            prefeature=pre(), events=e, freeze_at_utc=FREEZE, expected_starting_count=8
        )
