from datetime import datetime, timezone

import pytest

from app.core.sport_history_event_contract import (
    football_history_event_from_observation,
    tennis_history_event_from_observation,
)


UTC = timezone.utc


def observation(
    *,
    sport="tennis",
    payload=None,
    observed_at="2026-08-10T12:00:00Z",
    available_at="2026-08-10T13:00:00Z",
    fingerprint_char="a",
):
    if payload is None:
        payload = {
            "event_key": "MATCH:1",
            "event_at": "2026-08-10T10:00:00Z",
            "season_key": "2026",
            "competition_key": "ATP:TEST",
            "opponent_canonical_id": "tennis:player:opponent",
            "outcome": "W",
            "completed": True,
            "retirement": False,
            "surface": "hard",
            "indoor": False,
            "metrics": {
                "aces": 7,
                "double_faults": None,
            },
        }

    return {
        "sport": sport,
        "observed_at": observed_at,
        "available_at": available_at,
        "record_fingerprint": fingerprint_char * 64,
        "payload": payload,
    }


def test_tennis_contract_preserves_missing_metrics():
    event = tennis_history_event_from_observation(
        observation()
    )

    assert event.metrics["double_faults"] is None
    assert event.surface == "hard"
    assert event.completed is True
    assert len(event.event_fingerprint) == 64


def test_tennis_contract_rejects_future_event():
    value = observation()
    value["payload"] = dict(value["payload"])
    value["payload"]["event_at"] = (
        "2026-08-10T14:00:00Z"
    )

    with pytest.raises(
        ValueError,
        match="HISTORY_EVENT_AFTER_OBSERVATION",
    ):
        tennis_history_event_from_observation(value)


def test_tennis_contract_rejects_cross_sport():
    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        tennis_history_event_from_observation(
            observation(sport="football")
        )


def test_football_contract_has_separate_semantics():
    payload = {
        "event_key": "MATCH:F:1",
        "event_at": "2026-08-10T10:00:00Z",
        "season_key": "2026",
        "competition_key": "LEAGUE:1",
        "opponent_canonical_id": "football:team:opponent",
        "outcome": "D",
        "completed": True,
        "venue": "away",
        "metrics": {
            "goals_for": 1,
            "goals_against": 1,
            "xg_for": 1.2,
        },
    }

    event = football_history_event_from_observation(
        observation(
            sport="football",
            payload=payload,
        )
    )

    assert event.venue == "away"
    assert event.outcome == "D"
    assert not hasattr(event, "surface")


def test_nonfinite_metric_is_rejected():
    value = observation()
    value["payload"] = dict(value["payload"])
    value["payload"]["metrics"] = {
        "aces": float("inf")
    }

    with pytest.raises(
        ValueError,
        match="NONFINITE_HISTORY_METRIC_VALUE",
    ):
        tennis_history_event_from_observation(value)
