from __future__ import annotations

from datetime import date, datetime, timezone

from tools.sofascore_multisport_discovery import (
    SofaScoreClient,
    build_multisport_discovery,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        import json
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if "/sport/football/scheduled-events/" in url:
            day = url.rsplit("/", 1)[-1]
            rows = []
            if day == "2026-10-05":
                rows = [
                    {
                        "id": 501,
                        "startTimestamp": int(
                            datetime(
                                2026, 10, 5, 15, 0, tzinfo=timezone.utc
                            ).timestamp()
                        ),
                        "homeTeam": {"id": 10, "name": "Home FC"},
                        "awayTeam": {"id": 11, "name": "Away FC"},
                        "tournament": {
                            "id": 20,
                            "name": "League",
                            "uniqueTournament": {
                                "id": 21,
                                "name": "League",
                            },
                            "category": {"id": 30, "name": "Colombia"},
                        },
                        "status": {"type": "notstarted"},
                    }
                ]
            return FakeResponse({"events": rows})

        if "/sport/tennis/scheduled-tournaments/" in url:
            day = url.split("/scheduled-tournaments/")[1].split("/page/")[0]
            page = int(url.rsplit("/", 1)[-1])
            if day == "2026-10-05" and page == 1:
                event = {
                    "id": 601,
                    "startTimestamp": int(
                        datetime(
                            2026, 10, 5, 9, 0, tzinfo=timezone.utc
                        ).timestamp()
                    ),
                    "homeTeam": {
                        "id": 100,
                        "name": "Player A",
                        "country": {"name": "Spain", "alpha2": "ES"},
                    },
                    "awayTeam": {
                        "id": 101,
                        "name": "Player B",
                        "country": {"name": "France", "alpha2": "FR"},
                    },
                    "tournament": {
                        "id": 200,
                        "name": "Villena",
                        "uniqueTournament": {
                            "id": 201,
                            "name": "ATP Challenger Villena",
                        },
                        "category": {"id": 202, "name": "ATP Challenger"},
                        "groundType": "Hard",
                    },
                    "status": {"type": "notstarted"},
                }
                return FakeResponse({
                    "scheduledTournaments": [
                        {"name": "Villena", "events": [event]}
                    ],
                    "hasNextPage": False,
                })
            return FakeResponse({
                "scheduledTournaments": [],
                "hasNextPage": False,
            })

        if "/event/501" in url:
            return FakeResponse({"event": {"id": 501}})
        if "/event/601" in url:
            return FakeResponse({"event": {"id": 601}})
        if "/team/10/players" in url:
            return FakeResponse({"players": [{"player": {"id": 1}}]})
        if "/team/10" in url:
            return FakeResponse({"team": {"id": 10, "name": "Home FC"}})
        if "/player/100" in url:
            return FakeResponse({"player": {"id": 100, "name": "Player A"}})
        raise AssertionError(url)


def test_multisport_discovery_normalizes_bogota_day_and_entities():
    client = SofaScoreClient(session=FakeSession())
    result = build_multisport_discovery(
        client=client,
        target_date_bogota=date(2026, 10, 5),
        verify_entity_enrichment=True,
    )

    assert result["status"] == "PASS"
    assert result["football"]["event_count"] == 1
    assert result["football"]["events"][0]["home"]["name"] == "Home FC"
    assert result["football"]["events"][0]["event_start_bogota"].startswith(
        "2026-10-05T10:00:00"
    )
    assert result["tennis"]["event_count"] == 1
    tennis = result["tennis"]["events"][0]
    assert tennis["home"]["name"] == "Player A"
    assert tennis["away"]["name"] == "Player B"
    assert tennis["surface"] == "Hard"
    assert tennis["event_start_bogota"].startswith("2026-10-05T04:00:00")
    assert result["entity_enrichment_probe"]["football"]["roster_items"] == 1
    assert result["entity_enrichment_probe"]["tennis"]["player_id"] == 100
    assert result["protections"]["feeds_model_automatically"] is False
    assert result["protections"]["real_money"] == "BLOCKED"


def test_tennis_schedule_recurses_nested_events_and_deduplicates_event_id():
    session = FakeSession()
    client = SofaScoreClient(session=session)
    result = build_multisport_discovery(
        client=client,
        target_date_bogota=date(2026, 10, 5),
        verify_entity_enrichment=False,
    )

    ids = [row["sofascore_event_id"] for row in result["tennis"]["events"]]
    assert ids == [601]
    assert result["tennis"]["tournament_count"] == 1
    assert result["football"]["competition_count"] == 1
