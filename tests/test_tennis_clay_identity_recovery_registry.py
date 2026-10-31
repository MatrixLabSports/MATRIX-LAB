from __future__ import annotations

from tools.tennis_clay_identity_recovery_registry import build_registry


def test_recovery_registry_is_identity_only_and_exact_cut_ranked():
    catchup={
        "unmapped_identity_backlog_count":1,
        "unmapped_identity_backlog":[{
            "provider_player_id":"rapidapi-tennis:player:11",
            "numeric_player_id":"11",
            "observed_names":["Player One"],
            "observed_iocs":["USA"],
            "catchup_matches":7,
            "target_component_hits":3,
            "identity_observation_status":"CONSISTENT",
        }],
    }
    rankings={"11":{
        "place":"101","points":"500","player":"Player One",
        "country":"USA","snapshot_date":"2026-09-21",
    }}
    out=build_registry(catchup=catchup,ranking_by_player=rankings,revision="2026101290",max_targets=12)
    assert out["selected_count"]==1
    event=out["events"][0]
    assert event["identity_only"] is True
    assert event["model_admission_forbidden"] is True
    assert event["features_loaded"] is False
    assert event["outcome"] is None
    assert event["player_identities"][0]["provider_ranking"]["snapshot_date"]=="2026-09-21"
    assert out["metrics_opened"] is False
    assert out["real_money"]=="BLOCKED"
