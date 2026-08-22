from datetime import datetime, timezone

import pytest

from app.providers.api_football.live_service import (
    fetch_api_football_live_bundle,
)


NOW = datetime(
    2026, 8, 22, 19, 0,
    tzinfo=timezone.utc,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, params=None):
        self.calls.append(
            (endpoint, dict(params or {}))
        )
        if endpoint == "/fixtures":
            response = [
                {
                    "fixture": {
                        "id": 100,
                        "status": {
                            "short": "1H",
                            "elapsed": 20,
                        },
                    },
                    "teams": {
                        "home": {
                            "id": 1,
                            "name": "Home",
                        },
                        "away": {
                            "id": 2,
                            "name": "Away",
                        },
                    },
                    "goals": {
                        "home": 0,
                        "away": 0,
                    },
                }
            ]
        elif endpoint == "/fixtures/statistics":
            response = []
        elif endpoint == "/fixtures/events":
            response = []
        elif endpoint == "/odds/live":
            response = []
        else:
            raise AssertionError(endpoint)
        return {
            "response": response,
            "results": len(response),
            "errors": [],
        }


def test_one_shot_bundle_uses_exact_live_contract_paths():
    client = FakeClient()
    bundle = fetch_api_football_live_bundle(
        client=client,
        fixture_id=100,
        clock=lambda: NOW,
    )
    assert bundle.fixture_id == 100
    assert bundle.captured_at == NOW
    assert [row[0] for row in client.calls] == [
        "/fixtures",
        "/fixtures/statistics",
        "/fixtures/events",
        "/odds/live",
    ]
    assert bundle.automatic_wagering is False
    assert set(
        bundle.payload_fingerprints
    ) == {
        "fixture",
        "statistics",
        "events",
        "live_odds",
    }


def test_invalid_fixture_id_fails_before_network():
    client = FakeClient()
    with pytest.raises(
        ValueError,
        match="INVALID_API_FOOTBALL_FIXTURE_ID",
    ):
        fetch_api_football_live_bundle(
            client=client,
            fixture_id=0,
        )
    assert client.calls == []


def test_non_mapping_items_fail_closed():
    class BadClient(FakeClient):
        def get(self, endpoint, params=None):
            if endpoint == "/fixtures":
                return {
                    "response": ["bad"],
                    "results": 1,
                    "errors": [],
                }
            return super().get(
                endpoint,
                params,
            )

    with pytest.raises(ValueError):
        fetch_api_football_live_bundle(
            client=BadClient(),
            fixture_id=100,
        )
