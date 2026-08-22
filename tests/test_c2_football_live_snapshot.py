from datetime import datetime, timezone

from app.application.football.live_snapshot import (
    derive_live_pressure_features,
    snapshot_from_api_football_bundle,
)
from app.providers.api_football.live_service import (
    ApiFootballLiveBundle,
)


NOW = datetime(
    2026, 8, 22, 19, 0,
    tzinfo=timezone.utc,
)


def bundle():
    return ApiFootballLiveBundle(
        fixture_id=100,
        captured_at=NOW,
        fixture={
            "fixture": {
                "status": {
                    "short": "1H",
                    "elapsed": 32,
                }
            },
            "teams": {
                "home": {
                    "id": 1,
                    "name": "Dortmund",
                },
                "away": {
                    "id": 2,
                    "name": "Bayern",
                },
            },
            "goals": {
                "home": 0,
                "away": 0,
            },
        },
        statistics=(
            {
                "team": {
                    "id": 1,
                    "name": "Dortmund",
                },
                "statistics": [
                    {
                        "type": "Ball Possession",
                        "value": "31%",
                    },
                    {
                        "type": "Total Shots",
                        "value": 1,
                    },
                    {
                        "type": "Shots on Goal",
                        "value": None,
                    },
                    {
                        "type": "Corner Kicks",
                        "value": 0,
                    },
                    {
                        "type": "Shots insidebox",
                        "value": 1,
                    },
                ],
            },
            {
                "team": {
                    "id": 2,
                    "name": "Bayern",
                },
                "statistics": [
                    {
                        "type": "Ball Possession",
                        "value": "69%",
                    },
                    {
                        "type": "Total Shots",
                        "value": 8,
                    },
                    {
                        "type": "Shots on Goal",
                        "value": 5,
                    },
                    {
                        "type": "Corner Kicks",
                        "value": 3,
                    },
                    {
                        "type": "Shots insidebox",
                        "value": 4,
                    },
                ],
            },
        ),
        events=(),
        live_odds=(),
        payload_fingerprints={
            "fixture": "1" * 64,
            "statistics": "2" * 64,
            "events": "3" * 64,
            "live_odds": "4" * 64,
        },
        live_odds_requested=True,
    )


def test_snapshot_preserves_missing_not_zero():
    snapshot = snapshot_from_api_football_bundle(
        bundle()
    )
    assert (
        snapshot.home_statistics.shots_on_goal
        is None
    )
    assert (
        snapshot.away_statistics.shots_on_goal
        == 5.0
    )


def test_pressure_features_are_descriptive_not_thresholded():
    snapshot = snapshot_from_api_football_bundle(
        bundle()
    )
    features = derive_live_pressure_features(
        snapshot
    )
    assert features.possession_delta_home == -38.0
    assert features.total_shots_delta_home == -7.0
    assert features.corners_delta_home == -3.0
    assert features.home_shot_share == 1 / 9
