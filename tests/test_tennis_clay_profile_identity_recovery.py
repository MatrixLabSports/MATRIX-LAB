from __future__ import annotations

from tools.tennis_clay_profile_identity_recovery import recover


MODEL={
    "candidate_identity":"ATP_CHALLENGER_CLAY_ELO_V1",
    "rating_initial":1500.0,
    "same_day_update_policy":"BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE",
}


def _catch(pid,name,ioc):
    return {
        "silent_imputation":False,
        "unmapped_identity_backlog":[{
            "provider_player_id":f"rapidapi-tennis:player:{pid}",
            "numeric_player_id":pid,
            "observed_names":[name],
            "observed_iocs":[ioc],
            "identity_observation_status":"CONSISTENT",
            "target_component_hits":10,
            "catchup_matches":1,
        }],
    }


def _profile(pid,name,ioc,dob="2008-08-01",plays="Right-handed"):
    return {"data":{
        "id":pid,
        "name":name,
        "countryAcr":ioc,
        "birthday":dob,
        "information":{"plays":plays},
        "currentRank":999,
    }}


def test_profile_recovery_links_unique_historical_identity_with_dob_hand_age():
    hist=[
        {
            "tourney_date":"20260112",
            "player_a_id":"P0MJ","player_a_name":"Dante Pagani",
            "player_a_hand":"R","player_a_age":"17.451",
            "player_b_id":"X","player_b_name":"Other","player_b_hand":"R","player_b_age":"20",
        },
        {
            "tourney_date":"20260216",
            "player_a_id":"Y","player_a_name":"Other 2",
            "player_a_hand":"R","player_a_age":"21",
            "player_b_id":"P0MJ","player_b_name":"Dante Pagani",
            "player_b_hand":"R","player_b_age":"17.547",
        },
    ]
    out=recover(
        catchup=_catch("103814","Dante Pagani","ARG"),
        historical_rows=hist,
        model=MODEL,
        profile_fetcher=lambda _: _profile("103814","Dante Pagani","ARG"),
        max_targets=10,
    )
    assert out["passed_events"]==1
    row=out["mappings"][0]
    assert row["canonical_source_id"]=="P0MJ"
    assert row["new_to_clay_historical_dataset"] is False
    assert row["profile_competitive_fields_discarded"]==["currentRank"]


def test_profile_recovery_uses_frozen_1500_only_for_truly_new_clay_identity():
    out=recover(
        catchup=_catch("93283","Nicolas Garcia Longo","ARG"),
        historical_rows=[],
        model=MODEL,
        profile_fetcher=lambda _: _profile("93283","Nicolas Garcia Longo","ARG","2005-01-01"),
        max_targets=10,
    )
    assert out["passed_events"]==1
    row=out["mappings"][0]
    assert row["canonical_source_id"]=="RAPIDAPI_CLAY_NEW_93283"
    assert row["new_to_clay_historical_dataset"] is True
    assert row["frozen_initial_rating"]==1500.0


def test_profile_recovery_fails_closed_on_historical_hand_conflict():
    hist=[{
        "tourney_date":"20260112",
        "player_a_id":"P0MJ","player_a_name":"Dante Pagani",
        "player_a_hand":"L","player_a_age":"17.451",
        "player_b_id":"X","player_b_name":"Other","player_b_hand":"R","player_b_age":"20",
    }]
    out=recover(
        catchup=_catch("103814","Dante Pagani","ARG"),
        historical_rows=hist,
        model=MODEL,
        profile_fetcher=lambda _: _profile("103814","Dante Pagani","ARG"),
        max_targets=10,
    )
    assert out["passed_events"]==0
    assert out["blocked"][0]["reason"]=="PROFILE_HISTORICAL_HAND_CONFLICT"


def test_profile_recovery_requires_frozen_model_prior():
    bad=dict(MODEL); bad["rating_initial"]=1499.0
    try:
        recover(
            catchup=_catch("1","New Player","ARG"),
            historical_rows=[],
            model=bad,
            profile_fetcher=lambda _: _profile("1","New Player","ARG"),
            max_targets=1,
        )
    except ValueError as exc:
        assert "INITIAL_RATING_INVALID" in str(exc)
    else:
        raise AssertionError("expected fail-closed model prior validation")

def test_historical_identity_can_use_unique_historical_hand_when_profile_omits_hand():
    hist=[
        {
            "tourney_date":"20260112",
            "player_a_id":"P0MJ","player_a_name":"Dante Pagani",
            "player_a_hand":"R","player_a_age":"17.451",
            "player_b_id":"X","player_b_name":"Other","player_b_hand":"R","player_b_age":"20",
        },
        {
            "tourney_date":"20260216",
            "player_a_id":"Y","player_a_name":"Other 2",
            "player_a_hand":"R","player_a_age":"21",
            "player_b_id":"P0MJ","player_b_name":"Dante Pagani",
            "player_b_hand":"R","player_b_age":"17.547",
        },
    ]
    out=recover(
        catchup=_catch("103814","Dante Pagani","ARG"),
        historical_rows=hist,
        model=MODEL,
        profile_fetcher=lambda _: _profile("103814","Dante Pagani","ARG",plays=""),
        max_targets=10,
    )
    assert out["passed_events"]==1
    row=out["mappings"][0]
    assert row["canonical_source_id"]=="P0MJ"
    assert row["canonical_hand"]=="R"
    assert row["hand_source"]=="UNIQUE_PRE_CUT_CLAY_HISTORY"
    assert row["new_to_clay_historical_dataset"] is False


def test_new_player_still_requires_profile_hand():
    out=recover(
        catchup=_catch("93283","Nicolas Garcia Longo","ARG"),
        historical_rows=[],
        model=MODEL,
        profile_fetcher=lambda _: _profile("93283","Nicolas Garcia Longo","ARG","2005-01-01",plays=""),
        max_targets=10,
    )
    assert out["passed_events"]==0
    assert out["blocked"][0]["reason"]=="PROFILE_HAND_INVALID_FOR_NEW_PLAYER"


# MATRIX_CACHE_PHYSICAL_PROOF_TRIGGER_20261020T2230BOG
