from __future__ import annotations

from datetime import date

from tools.tennis_world_inventory_rapidapi import build_world_inventory


def _row(
    match_id,
    start,
    *,
    tournament_id,
    name,
    tier,
    surface,
    group="singles",
    p1=1,
    p2=2,
):
    return {
        "id": match_id,
        "matchId": match_id,
        "date": start,
        "startTime": start,
        "playerGroup": group,
        "player1Id": p1,
        "player2Id": p2,
        "player1": {"id": p1, "name": f"P{p1}", "countryAcr": "COL"},
        "player2": {"id": p2, "name": f"P{p2}", "countryAcr": "ESP"},
        "tournamentId": tournament_id,
        "tournament": {
            "id": tournament_id,
            "name": name,
            "tier": tier,
            "court": {"name": surface},
        },
        "round": {"name": "Round 1"},
        "status": "scheduled",
    }


class FakeWorldClient:
    def __init__(self):
        self.request_count = 0
        self.calls = []

    def fixtures_for_tour(
        self,
        tour,
        start,
        stop,
        *,
        filter_value=None,
        max_pages=12,
    ):
        self.request_count += 1
        self.calls.append((tour, start, stop, filter_value, max_pages))
        rows = {
            "atp": [
                _row(
                    1001,
                    "2026-10-02T05:00:00+00:00",
                    tournament_id=500,
                    name="Test Challenger",
                    tier="Challenger 75",
                    surface="Hard",
                    p1=11,
                    p2=12,
                ),
                _row(
                    1002,
                    "2026-10-03T04:59:59+00:00",
                    tournament_id=501,
                    name="Late Challenger",
                    tier="Challenger 100",
                    surface="Hard",
                    p1=13,
                    p2=14,
                ),
                _row(
                    1003,
                    "2026-10-03T05:00:00+00:00",
                    tournament_id=502,
                    name="Tomorrow",
                    tier="Challenger 75",
                    surface="Hard",
                    p1=15,
                    p2=16,
                ),
            ],
            "wta": [
                _row(
                    2001,
                    "2026-10-02T16:00:00+00:00",
                    tournament_id=600,
                    name="WTA Test",
                    tier="WTA 250",
                    surface="Hard",
                    p1=21,
                    p2=22,
                ),
            ],
            "itf": [
                _row(
                    3001,
                    "2026-10-02T18:00:00+00:00",
                    tournament_id=700,
                    name="ITF W35 Test",
                    tier="ITF W35",
                    surface="Clay",
                    p1=31,
                    p2=32,
                ),
            ],
        }[tour]
        return {
            "data": rows,
            "pageNo": 1,
            "pageSize": len(rows),
            "hasNextPage": False,
        }


def test_world_inventory_covers_exact_bogota_day_and_all_tours():
    client = FakeWorldClient()
    report = build_world_inventory(
        client=client,
        target_date_bogota=date(2026, 10, 2),
    )

    assert report["status"] == "PASS"
    assert report["world_inventory_complete"] is True
    assert report["calendar_day_start_local"] == "2026-10-02T00:00:00-05:00"
    assert report["calendar_day_end_local"] == "2026-10-02T23:59:59-05:00"
    assert report["calendar_day_start_utc"] == "2026-10-02T05:00:00+00:00"
    assert report["calendar_day_end_utc"] == "2026-10-03T04:59:59+00:00"
    assert report["provider_query_date_start"] == "2026-10-01"
    assert report["provider_query_date_stop"] == "2026-10-03"
    assert report["world_calendar_inventory_count"] == 4
    assert report["events_by_tour"] == {"ATP": 2, "WTA": 1, "ITF": 1}
    assert {row["tour"] for row in report["events"]} == {"ATP", "WTA", "ITF"}
    assert len(client.calls) == 3
    assert all(call[3] is None for call in client.calls)


def test_world_inventory_keeps_cor0203_as_derived_lane_only():
    client = FakeWorldClient()
    report = build_world_inventory(
        client=client,
        target_date_bogota=date(2026, 10, 2),
    )

    lane = report["derived_lanes"]["COR02_COR03_ATP_CHALLENGER_HARD"]
    assert lane["domain_candidate_count"] == 2
    assert lane["feeds_model_automatically"] is False
    assert lane["governed_pipeline_remains_authoritative"] is True
    assert report["derived_lanes"]["WTA"]["feeds_COR02_COR03"] is False
    assert report["derived_lanes"]["ITF"]["feeds_COR02_COR03"] is False
    assert report["p_matrix"] == "NOT_GENERATED"
    assert report["metrics_opened"] is False
    assert report["real_money"] == "BLOCKED"


def test_world_inventory_marks_partial_if_one_tour_fails():
    class PartialClient(FakeWorldClient):
        def fixtures_for_tour(
            self,
            tour,
            start,
            stop,
            *,
            filter_value=None,
            max_pages=12,
        ):
            if tour == "itf":
                self.request_count += 1
                raise ValueError("ITF_ROUTE_UNAVAILABLE")
            return super().fixtures_for_tour(
                tour,
                start,
                stop,
                filter_value=filter_value,
                max_pages=max_pages,
            )

    report = build_world_inventory(
        client=PartialClient(),
        target_date_bogota=date(2026, 10, 2),
    )
    assert report["status"] == "PARTIAL"
    assert report["world_inventory_complete"] is False
    assert report["tour_summaries"]["ATP"]["status"] == "PASS"
    assert report["tour_summaries"]["WTA"]["status"] == "PASS"
    assert report["tour_summaries"]["ITF"]["status"] == "BLOCKED"
    assert "ITF" in report["tour_errors"]


def test_world_inventory_does_not_count_event_at_next_bogota_midnight():
    client = FakeWorldClient()
    report = build_world_inventory(
        client=client,
        target_date_bogota=date(2026, 10, 2),
    )
    ids = {row["match_id"] for row in report["events"]}
    assert "1003" not in ids
    assert "1001" in ids
    assert "1002" in ids
