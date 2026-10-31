import copy

from tools.api_football_over25_high_scoring_league_radar import (
    build_league_policy,
    build_radar,
    classify_league,
)


def _audit():
    return {
        "observed_at_utc":"2026-10-04T02:32:57+00:00",
        "ranking":[
            {
                "league_id":"744","label":"Oberliga Schleswig-Holstein",
                "provider_name":"Oberliga - Schleswig-Holstein","country":"Germany",
                "season":2026,"n":87,"over_2_5_pct":81.6,"avg_goals":4.21,
                "last10":{"over_2_5_pct":90.0},
                "last20":{"over_2_5_pct":90.0},
            },
            {
                "league_id":"344","label":"LFPB","provider_name":"Primera División",
                "country":"Bolivia","season":2026,"n":160,"over_2_5_pct":63.1,
                "avg_goals":3.11,"last10":{"over_2_5_pct":70.0},
                "last20":{"over_2_5_pct":80.0},
            },
            {
                "league_id":"1227","label":"Premier League Femenina",
                "provider_name":"Premier League Women","country":"Saudi-Arabia",
                "season":2027,"n":16,"over_2_5_pct":81.25,"avg_goals":4.81,
                "last10":{"over_2_5_pct":80.0},"last20":None,
            },
            {
                "league_id":"129","label":"Primera Nacional","provider_name":"Primera Nacional",
                "country":"Argentina","season":2026,"n":565,"over_2_5_pct":32.39,
                "avg_goals":1.93,"last10":{"over_2_5_pct":40.0},
                "last20":{"over_2_5_pct":35.0},
            },
        ],
    }


def _registry():
    return {
        "future_only":True,
        "target_date":"2026-10-04",
        "captured_at_utc":"2026-10-04T02:00:00+00:00",
        "events":[
            {
                "provider_fixture_id":"1","provider_league_id":"744",
                "event_start_utc":"2026-10-04T12:00:00+00:00",
                "competition":"Oberliga - Schleswig-Holstein","country":"Germany",
                "home_team":"A","away_team":"B",
            },
            {
                "provider_fixture_id":"2","provider_league_id":"129",
                "event_start_utc":"2026-10-04T13:00:00+00:00",
                "competition":"Primera Nacional","country":"Argentina",
                "home_team":"C","away_team":"D",
            },
        ],
    }


def test_policy_thresholds_are_governed():
    assert classify_league({"n":87,"over_2_5_pct":81.6,"last20":{"over_2_5_pct":90}})=="PRIORITY_A_PLUS"
    assert classify_league({"n":160,"over_2_5_pct":63.1,"last20":{"over_2_5_pct":80}})=="PRIORITY_A"
    assert classify_league({"n":16,"over_2_5_pct":81.25,"last20":None})=="EXPERIMENTAL_HIGH"
    assert classify_league({"n":565,"over_2_5_pct":32.39,"last20":{"over_2_5_pct":35}})=="NOT_PRIORITY"


def test_radar_does_not_mutate_world_registry_or_p_matrix():
    audit=_audit()
    registry=_registry()
    before=copy.deepcopy(registry)
    radar=build_radar(audit=audit,registry=registry)
    assert registry==before
    assert radar["world_future_fixture_count"]==2
    assert radar["priority_radar_fixture_count"]==1
    assert radar["candidates"][0]["provider_fixture_id"]=="1"
    assert radar["candidates"][0]["p_matrix_adjustment"]==0.0
    assert radar["candidates"][0]["bet_decision"]=="NOT_EVALUATED_BY_RADAR"
    assert radar["p_matrix_status"]=="NOT_GENERATED_BY_RADAR"
    assert radar["protections"]["changes_p_matrix"] is False
    assert radar["protections"]["reorders_history_queue"] is False
    assert radar["protections"]["filters_world_inventory"] is False
    assert radar["automatic_wagering"] is False
    assert radar["real_money"]=="BLOCKED"


def test_policy_marks_league_rate_as_context_only():
    policy=build_league_policy(_audit())
    selected=[x for x in policy["leagues"] if x["eligible_for_priority_radar"]]
    assert len(selected)==3
    assert all(x["eligible_to_modify_p_matrix"] is False for x in selected)
    assert policy["protections"]["league_rate_used_as_probability"] is False
