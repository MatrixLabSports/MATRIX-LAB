from tools.tennis_world_inventory_accumulate import accumulate


def _event(mid, p1, p2, *, family="ATP", detail="ATP_CHALLENGER", start="2026-10-02T15:00:00+00:00"):
    candidate = detail == "ATP_CHALLENGER"
    return {
        "source_event_id": f"rapidapi-tennis:atp:match:{mid}",
        "provider_channel": "ATP",
        "circuit_family": family,
        "circuit_detail": detail,
        "match_id": str(mid),
        "tournament_id": "500",
        "tournament_name": "Example Challenger",
        "round": "1/4",
        "event_format": "SINGLES",
        "event_start_utc": start,
        "player1": {"id": str(p1), "name": f"P{p1}"},
        "player2": {"id": str(p2), "name": f"P{p2}"},
        "model_derivation": {"domain_candidate": candidate, "lane": "COR02_COR03_ATP_CHALLENGER_HARD"},
    }


def _report(events, status="PASS"):
    return {
        "status": status,
        "world_inventory_complete": status == "PASS",
        "target_date_bogota": "2026-10-02",
        "events": events,
        "derived_lanes": {},
    }


def test_accumulator_never_shrinks_when_provider_drops_prior_rows():
    prior = _report([_event(1, 11, 12), _event(2, 21, 22), _event(3, 31, 32)])
    current = _report([_event(2, 21, 22), _event(4, 41, 42)])
    out = accumulate(current, prior)
    assert out["world_calendar_inventory_count"] == 4
    assert out["accumulation"]["prior_count"] == 3
    assert out["accumulation"]["current_fetch_count"] == 2
    assert out["accumulation"]["retained_prior_only_count"] == 2
    assert out["accumulation"]["never_decrease_within_day"] is True


def test_mutable_match_id_is_one_physical_event_and_preserves_aliases():
    prior = _report([_event(100, 11, 12)])
    current = _report([_event(999, 11, 12)])
    out = accumulate(current, prior)
    assert out["world_calendar_inventory_count"] == 1
    row = out["events"][0]
    assert row["match_id"] == "999"
    assert row["source_event_aliases"] == [
        "rapidapi-tennis:atp:match:100",
        "rapidapi-tennis:atp:match:999",
    ]


def test_accumulator_recalculates_cor_lane_from_cumulative_union():
    prior = _report([_event(1, 11, 12)])
    current = _report([_event(2, 21, 22), _event(3, 31, 32, family="ITF", detail="ITF_MEN")])
    out = accumulate(current, prior)
    lane = out["derived_lanes"]["COR02_COR03_ATP_CHALLENGER_HARD"]
    assert lane["domain_candidate_count"] == 2
    assert lane["feeds_model_automatically"] is False
    assert out["p_matrix"] == "NOT_GENERATED"
    assert out["metrics_opened"] is False
    assert out["real_money"] == "BLOCKED"


def test_partial_current_capture_does_not_erase_prior_events_or_fake_pass():
    prior = _report([_event(1, 11, 12), _event(2, 21, 22)])
    current = _report([_event(2, 21, 22)], status="PARTIAL")
    out = accumulate(current, prior)
    assert out["world_calendar_inventory_count"] == 2
    assert out["status"] == "PARTIAL"
    assert out["world_inventory_complete"] is False
