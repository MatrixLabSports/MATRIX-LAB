from __future__ import annotations

from tools.tennis_clay_prospective_producer import produce


def test_producer_admits_only_future_dual_bound_pit_ready_event():
    pre={
        "events":[{
            "event_id":"CLAY-1",
            "canonical_source_event_id":"rapidapi-tennis:atp:match:1",
            "competition":"Test Challenger",
            "round":"First",
            "surface":"Clay",
            "event_start_utc":"2026-10-12T18:00:00+00:00",
            "physical_event_key":"a"*64,
            "player_identities":[
                {"provider_player_id":"rapidapi-tennis:player:11"},
                {"provider_player_id":"rapidapi-tennis:player:22"},
            ],
        }]
    }
    cross={
        "events":[{"event_id":"CLAY-1","status":"PASS"}],
        "mappings":[
            {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","canonical_name":"Player A","status":"PASS"},
            {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","canonical_name":"Player B","status":"PASS"},
        ],
    }
    catch={
        "model_identity":"ATP_CHALLENGER_CLAY_ELO_V1",
        "chosen_k":32.0,
        "probability_scale":400.0,
        "silent_imputation":False,
        "outcomes_used_for_model_parameter_tuning":0,
        "catchup_source_stop":"2026-10-11",
        "historical_dataset_max_tourney_date":20260914,
        "targets":[
            {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","ready":True,"rating_after_catchup":1520.0},
            {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","ready":True,"rating_after_catchup":1480.0},
        ],
    }
    rec={
        "bindings":[{
            "surface_family":"CLAY",
            "rapid_source_event_id":"rapidapi-tennis:atp:match:1",
            "api_tennis_source_event_id":"api-tennis:event:9",
            "rapid_physical_event_key":"a"*64,
            "blockers":["PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT"],
            "identity_binding_basis":"PAIR_DATE_TIME_UNIQUE_TOURNAMENT_LABEL_VARIANT",
            "surface_binding":"PASS",
        }]
    }
    state={
        "metrics_opened":False,
        "outcomes_read":0,
        "real_money":"BLOCKED",
        "frozen_model_identity":"ATP_CHALLENGER_CLAY_ELO_V1",
        "observation_count":0,
    }
    model={"parameter_selection":{"chosen_k":32.0},"probability_scale":400.0}
    admitted,new_state,audit=produce(
        prefeature=pre,
        crosswalk=cross,
        catchup=catch,
        reconciliation=rec,
        state=state,
        model=model,
        prior=[],
        freeze_at_utc="2026-10-12T08:00:00+00:00",
    )
    assert len(admitted)==1
    assert admitted[0]["outcome"] is None
    assert admitted[0]["model"]["p_player_a"]>0.5
    assert admitted[0]["identity"]["dual_paid_provider_binding"]=="PASS"
    assert new_state["observation_count"]==1
    assert new_state["metrics_opened"] is False
    assert audit["historical_backfill"] is False
    assert audit["real_money"]=="BLOCKED"


def test_producer_blocks_unready_pit_target():
    pre={"events":[{
        "event_id":"CLAY-1","canonical_source_event_id":"rapidapi-tennis:atp:match:1",
        "competition":"X","round":"First","surface":"Clay",
        "event_start_utc":"2026-10-12T18:00:00+00:00","physical_event_key":"a"*64,
        "player_identities":[{"provider_player_id":"rapidapi-tennis:player:11"},{"provider_player_id":"rapidapi-tennis:player:22"}],
    }]}
    cross={"events":[{"event_id":"CLAY-1","status":"PASS"}],"mappings":[
        {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","canonical_name":"A","status":"PASS"},
        {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","canonical_name":"B","status":"PASS"},
    ]}
    catch={"model_identity":"ATP_CHALLENGER_CLAY_ELO_V1","chosen_k":32.0,"silent_imputation":False,
           "outcomes_used_for_model_parameter_tuning":0,"targets":[
             {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","ready":True,"rating_after_catchup":1500.0},
             {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","ready":False,"rating_after_catchup":None},
           ]}
    rec={"bindings":[{"surface_family":"CLAY","rapid_source_event_id":"rapidapi-tennis:atp:match:1",
                      "api_tennis_source_event_id":"api-tennis:event:9","rapid_physical_event_key":"a"*64,
                      "blockers":["PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT"],"surface_binding":"PASS"}]}
    state={"metrics_opened":False,"outcomes_read":0,"real_money":"BLOCKED",
           "frozen_model_identity":"ATP_CHALLENGER_CLAY_ELO_V1"}
    model={"parameter_selection":{"chosen_k":32.0},"probability_scale":400.0}
    admitted,new_state,audit=produce(prefeature=pre,crosswalk=cross,catchup=catch,reconciliation=rec,
                                     state=state,model=model,prior=[],freeze_at_utc="2026-10-12T08:00:00+00:00")
    assert admitted==[]
    assert new_state["observation_count"]==0
    assert any(x["reason"]=="PIT_OR_IDENTITY_BLOCKED" for x in audit["blocked"])
