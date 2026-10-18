from tools.cor0203_api_tennis_certified_authority_recovery import (
    recover_certified_authority_aliases,
)


def _discovery():
    return {
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[{
            "players":[
                {
                    "name":"Timofei Derepasko",
                    "provider_player_id":"api-tennis:player:52054",
                    "provider_ranking":{
                        "player":"Timofei Derepasko",
                        "place":"649",
                        "points":"55",
                    },
                },
                {
                    "name":"Omar Jasika",
                    "provider_player_id":"api-tennis:player:1261",
                    "provider_ranking":{
                        "player":"Omar Jasika",
                        "place":"392",
                        "points":"128",
                    },
                },
            ]
        }],
    }


def _authority():
    return {
        "schema":"MATRIX_COR0203_IDENTITY_AUTHORITY_AUTOEXPAND_V1",
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "records":[
            {
                "provider_player_id":"rapidapi-tennis:player:94367",
                "provider_display_name":"Timofei Derepasko",
                "canonical_name":"Timofei Derepasko",
                "provider_ioc_raw":"RUS",
                "provider_ioc_canonical":"RUS",
                "provider_rank":"649",
                "provider_rank_points":"55",
                "ranking_cut":"2026-09-21",
                "sealed_r706_history":{
                    "fully_history_ready":True,
                    "counts":{"hard_n":2,"overall_n":2},
                },
                "pre_cut_provider_history":{
                    "eligible_pre_cut_matches":13,
                    "provider_player_id":"rapidapi-tennis:player:94367",
                },
                "biographical_candidates":[{
                    "name":"Timofei Derepasko",
                    "dob":"20070107",
                    "hand":"R",
                    "ioc":"RUS",
                    "master_id":"RAPIDAPI_PROFILE_94367",
                }],
            },
            {
                "provider_player_id":"api-tennis:player:1261",
                "provider_display_name":"Omar Jasika",
                "canonical_name":"Omar Jasika",
                "provider_ioc_raw":"AUS",
                "provider_ioc_canonical":"AUS",
                "provider_rank":"392",
                "provider_rank_points":"128",
                "ranking_cut":"2026-09-21",
            },
        ],
    }


def _ranking_rows():
    return [{
        "position":649,
        "pts":55,
        "player":{"id":94367,"name":"Timofei Derepasko","countryAcr":"RUS"},
    }]


def _profile(pid):
    assert pid=="94367"
    return {
        "data":{
            "id":"94367",
            "name":"Timofei Derepasko",
            "countryAcr":"RUS",
            "birthday":"2007-01-07",
            "information":{"plays":"Right-Handed"},
        }
    }


def test_recovery_reuses_only_certified_r706_ready_authority():
    updated,aliases,audit=recover_certified_authority_aliases(
        discovery=_discovery(),
        authority=_authority(),
        aliases={
            "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
            "records":[],
            "post_cut_competitive_data_used":False,
            "outcomes_used":False,
            "odds_used":False,
        },
        ranking_rows=_ranking_rows(),
        profile_fetcher=_profile,
    )
    assert audit["status"]=="PASS"
    assert audit["recovered_count"]==1
    assert audit["recovered"][0]["api_tennis_provider_player_id"]=="api-tennis:player:52054"
    assert audit["recovered"][0]["rapidapi_provider_player_id"]=="rapidapi-tennis:player:94367"
    assert audit["recovered"][0]["pre_cut_provider_matches"]==13
    row=next(
        x for x in aliases["records"]
        if x["provider_player_id"]=="api-tennis:player:52054"
    )
    assert row["canonical_name"]=="Timofei Derepasko"
    assert row["authority_basis"]==(
        "API_TENNIS_TO_CERTIFIED_R706_RAPIDAPI_AUTHORITY_PROFILE_EXACT_CUT"
    )
    assert row["sealed_r706_history"]["fully_history_ready"] is True
    assert row["pre_cut_history"]["rows"]==13
    assert row["pre_cut_history"]["canonical_source_ids"]==[
        "rapidapi-tennis:player:94367"
    ]
    assert aliases["post_cut_competitive_data_used"] is False
    assert any(
        x["provider_player_id"]=="api-tennis:player:52054"
        for x in updated["records"]
    )


def test_recovery_fails_closed_without_certified_authority():
    discovery={
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[{
            "players":[{
                "name":"Unknown Player",
                "provider_player_id":"api-tennis:player:99999",
                "provider_ranking":{"player":"Unknown Player"},
            }]
        }],
    }
    updated,aliases,audit=recover_certified_authority_aliases(
        discovery=discovery,
        authority={
            "records":[],
            "post_cut_competitive_data_used":False,
            "outcomes_used":False,
            "odds_used":False,
        },
        aliases={
            "records":[],
            "post_cut_competitive_data_used":False,
            "outcomes_used":False,
            "odds_used":False,
        },
        ranking_rows=[],
        profile_fetcher=lambda pid: {},
    )
    assert audit["recovered_count"]==0
    assert audit["blocked_count"]==1
    assert aliases["records"]==[]
    assert updated["records"]==[]
