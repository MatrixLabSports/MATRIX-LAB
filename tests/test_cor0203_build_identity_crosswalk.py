from __future__ import annotations

from tools.cor0203_build_identity_crosswalk import build_crosswalk


def static_cut():
    return {
        "ranking_cut": "20260921",
        "source_sha256": "a" * 64,
        "silent_imputation": False,
        "post_cut_data_used": False,
        "players": {
            "D0DW": {
                "canonical_name": "Titouan Droguet",
                "hand": "R",
                "age": 25.268,
                "rank": 84,
                "rank_points": 690,
                "ioc": "FRA",
            },
            "P0HW": {
                "canonical_name": "Dino Prizmic",
                "hand": "R",
                "age": 21.128,
                "rank": 101,
                "rank_points": 603,
                "ioc": "CRO",
            },
        },
    }


def prefeature():
    return {
        "revision": "R800",
        "holdout_id": "H",
        "events": [
            {
                "event_id": "e1",
                "identity_crosswalk_required": True,
                "player_identities": [
                    {
                        "display_name": "Titouan Droguet",
                        "provider_player_id": "api-tennis:player:11",
                        "provider_ranking": {
                            "place": "84",
                            "points": "690",
                            "player": "Titouan Droguet",
                            "country": "France",
                        },
                    },
                    {
                        "display_name": "Dino Prizmic",
                        "provider_player_id": "api-tennis:player:22",
                        "provider_ranking": {
                            "place": "101",
                            "points": "603",
                            "player": "Dino Prizmic",
                            "country": "Croatia",
                        },
                    },
                ],
            }
        ],
    }


def test_exact_rank_points_plus_name_confirmation_passes():
    result = build_crosswalk(prefeature=prefeature(), static_cut=static_cut())

    assert result["status"] == "PASS"
    assert result["passed_events"] == 1
    assert result["blocked_events"] == 0
    assert result["join_by_name_only"] is False
    mappings = {m["provider_player_id"]: m for m in result["mappings"]}
    assert mappings["api-tennis:player:11"]["canonical_source_id"] == "D0DW"
    assert mappings["api-tennis:player:22"]["canonical_source_id"] == "P0HW"
    assert mappings["api-tennis:player:11"]["match_basis"] == "EXACT_RANK_AND_POINTS_PLUS_NAME_CONFIRMATION"


def test_name_match_alone_cannot_pass_wrong_rank_points():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["provider_ranking"]["place"] = "999"

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    event = result["events"][0]
    assert "STATIC_IDENTITY_NO_MATCH:api-tennis:player:11" in event["blockers"]


def test_exact_rank_points_cannot_override_name_mismatch():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["display_name"] = "Wrong Person"
    pre["events"][0]["player_identities"][0]["provider_ranking"]["player"] = "Wrong Person"

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    assert "IDENTITY_NAME_CONFIRMATION_FAIL:api-tennis:player:11" in result["events"][0]["blockers"]


def test_nonunique_rank_points_are_blocked():
    cut = static_cut()
    cut["players"]["OTHER"] = {
        "canonical_name": "Other Player",
        "hand": "R",
        "age": 30.0,
        "rank": 84,
        "rank_points": 690,
        "ioc": "USA",
    }

    result = build_crosswalk(prefeature=prefeature(), static_cut=cut)

    assert result["status"] == "ALL_BLOCKED"
    assert "STATIC_IDENTITY_NONUNIQUE:api-tennis:player:11" in result["events"][0]["blockers"]


def test_missing_provider_ranking_blocks_without_name_fallback():
    pre = prefeature()
    pre["events"][0]["player_identities"][0]["provider_ranking"] = None

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "ALL_BLOCKED"
    assert "PROVIDER_RANKING_MISSING:api-tennis:player:11" in result["events"][0]["blockers"]


def test_events_are_isolated_when_one_crosswalk_fails():
    pre = prefeature()
    second = {
        "event_id": "e2",
        "identity_crosswalk_required": True,
        "player_identities": [
            {
                "display_name": "Titouan Droguet",
                "provider_player_id": "api-tennis:player:11",
                "provider_ranking": {
                    "place": "84",
                    "points": "690",
                    "player": "Titouan Droguet",
                },
            },
            {
                "display_name": "Unknown Player",
                "provider_player_id": "api-tennis:player:33",
                "provider_ranking": {
                    "place": "777",
                    "points": "10",
                    "player": "Unknown Player",
                },
            },
        ],
    }
    pre["events"].append(second)

    result = build_crosswalk(prefeature=pre, static_cut=static_cut())

    assert result["status"] == "PASS_WITH_BLOCKERS"
    by_event = {row["event_id"]: row for row in result["events"]}
    assert by_event["e1"]["status"] == "PASS"
    assert by_event["e2"]["status"] == "BLOCKED"



def governed_identity_authority():
    return {
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "records": [
            {
                "provider_player_id": "rapidapi-tennis:player:26925",
                "provider_display_name": "Michael Mmoh",
                "provider_ioc_raw": "USA",
                "provider_ioc_canonical": "USA",
                "ranking_cut": "2026-09-21",
                "provider_rank": "148",
                "provider_rank_points": "379",
                "pre_cut_history": {
                    "canonical_source_ids": ["MP01"],
                    "canonical_iocs": ["USA"],
                    "observed_hands": ["R"],
                    "rows": 39,
                    "latest_row_date": 20260914,
                },
                "biographical_candidates": [
                    {
                        "master_id": "111581",
                        "name": "Michael Mmoh",
                        "hand": "R",
                        "dob": "19980110",
                        "ioc": "USA",
                    }
                ],
            }
        ],
    }


def rapidapi_prefeature_for_authority():
    return {
        "revision": "R900",
        "holdout_id": "H",
        "discovery_provider": "rapidapi_tennis",
        "events": [
            {
                "event_id": "rapid-e1",
                "identity_crosswalk_required": True,
                "player_identities": [
                    {
                        "display_name": "Michael Mmoh",
                        "provider": "rapidapi_tennis",
                        "provider_player_id": "rapidapi-tennis:player:26925",
                        "provider_ranking": {
                            "place": "148",
                            "points": "379",
                            "player": "Michael Mmoh",
                            "country": "USA",
                            "snapshot_date": "2026-09-21",
                        },
                    },
                    {
                        "display_name": "Dino Prizmic",
                        "provider": "api_tennis",
                        "provider_player_id": "api-tennis:player:22",
                        "provider_ranking": {
                            "place": "101",
                            "points": "603",
                            "player": "Dino Prizmic",
                            "country": "CRO",
                        },
                    },
                ],
            }
        ],
    }


def test_governed_authority_can_resolve_player_absent_from_exact_static_cut():
    result = build_crosswalk(
        prefeature=rapidapi_prefeature_for_authority(),
        static_cut=static_cut(),
        identity_authority=governed_identity_authority(),
    )

    assert result["status"] == "PASS"
    mappings = {m["provider_player_id"]: m for m in result["mappings"]}
    mmoh = mappings["rapidapi-tennis:player:26925"]
    assert mmoh["canonical_source_id"] == "MP01"
    assert mmoh["canonical_name"] == "Michael Mmoh"
    assert mmoh["canonical_hand"] == "R"
    assert mmoh["canonical_age"] == 28.695
    assert mmoh["canonical_rank"] == 148
    assert mmoh["canonical_rank_points"] == 379
    assert mmoh["ranking_cut"] == "20260921"
    assert "EXACT_PROVIDER_ID_PLUS_NAME_IOC" in mmoh["match_basis"]


def test_governed_authority_fails_closed_on_country_mismatch():
    authority = governed_identity_authority()
    authority["records"][0]["provider_ioc_canonical"] = "CAN"

    result = build_crosswalk(
        prefeature=rapidapi_prefeature_for_authority(),
        static_cut=static_cut(),
        identity_authority=authority,
    )

    assert result["status"] == "ALL_BLOCKED"
    blockers = result["events"][0]["blockers"]
    assert "STATIC_IDENTITY_NO_MATCH:rapidapi-tennis:player:26925" in blockers
    assert "IDENTITY_AUTHORITY_IOC_MISMATCH:rapidapi-tennis:player:26925" in blockers


def test_governed_authority_fails_closed_when_biographical_dob_is_missing():
    authority = governed_identity_authority()
    authority["records"][0]["biographical_candidates"][0]["dob"] = None

    result = build_crosswalk(
        prefeature=rapidapi_prefeature_for_authority(),
        static_cut=static_cut(),
        identity_authority=authority,
    )

    assert result["status"] == "ALL_BLOCKED"
    blockers = result["events"][0]["blockers"]
    assert "IDENTITY_AUTHORITY_DOB_INVALID:rapidapi-tennis:player:26925" in blockers


def test_r730_r731_authority_releases_only_evidenced_events():
    pre=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R730.json"))
    static=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json"))
    authority=_load(Path("evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R731.json"))
    out=build_crosswalk(prefeature=pre,static_cut=static,identity_authority=authority)
    assert out["passed_events"] == 12
    assert out["blocked_events"] == 5
    assert out["status"] == "PASS_WITH_BLOCKERS"
    blocked={row["event_id"]:row["blockers"] for row in out["events"] if row["status"]=="BLOCKED"}
    assert set(blocked) == {
        "COR0203-RAPIDAPI-TENNIS-1415",
        "COR0203-RAPIDAPI-TENNIS-1469",
        "COR0203-RAPIDAPI-TENNIS-1471",
        "COR0203-RAPIDAPI-TENNIS-1466",
        "COR0203-RAPIDAPI-TENNIS-1475",
    }


def test_r730_r733_authority_releases_ultra_evidenced_profiles_only():
    pre=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R730.json"))
    static=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json"))
    authority=_load(Path("evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R733.json"))
    out=build_crosswalk(prefeature=pre,static_cut=static,identity_authority=authority)
    assert out["passed_events"] == 15
    assert out["blocked_events"] == 2
    blocked={row["event_id"] for row in out["events"] if row["status"]=="BLOCKED"}
    assert blocked == {
        "COR0203-RAPIDAPI-TENNIS-1471",
        "COR0203-RAPIDAPI-TENNIS-1466",
    }
    assert all(
        row.get("identity_authority")=="MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R733"
        for row in out["mappings"]
        if row.get("identity_authority")
    )


def test_r734_maps_provider_marat_display_to_precut_canonical_name():
    pre=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R730.json"))
    static=_load(Path("evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json"))
    authority=_load(Path("evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R734.json"))
    out=build_crosswalk(prefeature=pre,static_cut=static,identity_authority=authority)
    marat=next(
        row for row in out["mappings"]
        if row["provider_player_id"]=="rapidapi-tennis:player:80183"
    )
    assert marat["provider_display_name"]=="Marat Sharipov (RUS)"
    assert marat["canonical_name"]=="Marat Sharipov"
    assert marat["canonical_source_id"]=="S0MN"
    assert marat["identity_authority"]=="MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R734"
