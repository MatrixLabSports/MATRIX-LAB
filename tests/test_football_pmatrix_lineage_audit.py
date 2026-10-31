from datetime import datetime, timezone

import pytest

from tools.football_pmatrix_lineage_audit import build_audit


def _prereg(total=662,prospective=654,kickoff_missing=0,postponed=8):
    return {
        "status":"PASS_BROWSER_FIRST_PREREGISTRATION",
        "target_date_bogota":"2026-10-28",
        "generated_from_watchlist_at_utc":"2026-10-28T03:33:48+00:00",
        "counts":{
            "total_monitoring_events":total,
            "prospective_before_displayed_kickoff":prospective,
            "kickoff_not_certified":kickoff_missing,
            "postponed_no_prospective_kickoff":postponed,
            "not_prospective_at_preregistration":0,
        },
        "policy":{"source_order":["SOFASCORE","FLASHSCORE","APIS"]},
    }


def _cycle(total=662,prospective=654,kickoff_missing=0,postponed=8):
    return {
        "status":"PASS",
        "target_date_bogota":"2026-10-28",
        "cycle_id":"20261028T040000Z",
        "started_at_utc":"2026-10-28T04:00:00+00:00",
        "finished_at_utc":"2026-10-28T04:01:00+00:00",
        "browser_first":{
            "total_monitoring_events":total,
            "prospective_before_displayed_kickoff":prospective,
            "kickoff_not_certified":kickoff_missing,
            "postponed_no_prospective_kickoff":postponed,
            "not_prospective_at_preregistration":0,
        },
        "fixture_capture":{"eligible_future_fixtures":515},
        "canonical":{"ready_input_count":2,"blocked_future_input_count":513},
    }


def _pmatrix():
    path="evidence/api_football/prospective_daily/2026-10-28/20261028T040000Z"
    return {
        "p_matrix_status":"GENERATED_SHADOW",
        "generated_at_utc":"2026-10-28T04:01:00+00:00",
        "inventory_cycle":path,
        "probability_source_cycle":path,
        "model":"calibrated_log_pool_v1",
        "markets_generated":["1x2","over_2_5"],
        "source_ready_input_count":2,
        "scored_count":1,
        "blocked_count":1,
        "protections":{
            "odds_used_to_generate_probability":False,
            "target_outcomes_used":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "rows":[{
            "fixture_id":"1",
            "kickoff_utc":"2026-10-28T05:00:00+00:00",
            "odds_used_to_generate_probability":False,
            "outcomes_used_from_target":False,
        }],
        "blocked":[{"fixture_id":"2","reason":"BLOCKED_RAW_GROUP_MISSING"}],
    }


def test_lineage_passes_only_when_browser_cycle_matches_current_canonical():
    out=build_audit(
        preregistry=_prereg(),
        cycle=_cycle(),
        p_matrix=_pmatrix(),
        target_date="2026-10-28",
        generated_at=datetime(2026,10,28,4,2,tzinfo=timezone.utc),
    )
    assert out["status"]=="PASS_PMATRIX_PRE_ODDS_ELIGIBILITY"
    assert out["blockers"]==[]
    assert out["p_matrix"]["operationally_certified"] is True
    assert out["lineage"]["browser_counts_exact_match"] is True
    assert out["protections"]["odds_used_to_generate_probability"] is False


def test_lineage_blocks_stale_browser_preregistration_but_preserves_physical_pmatrix():
    out=build_audit(
        preregistry=_prereg(),
        cycle=_cycle(total=663,prospective=655,kickoff_missing=7,postponed=0),
        p_matrix=_pmatrix(),
        target_date="2026-10-28",
        generated_at=datetime(2026,10,28,4,2,tzinfo=timezone.utc),
    )
    assert out["status"]=="BLOCKED_PMATRIX_LINEAGE"
    assert out["blockers"]==["STALE_BROWSER_PREREGISTRATION_IN_PROBABILITY_CYCLE"]
    assert out["p_matrix"]["physically_generated"] is True
    assert out["p_matrix"]["operationally_certified"] is False
    assert out["interpretation"]["stale_cycle_must_be_regenerated_before_operational_use"] is True


def test_lineage_rejects_odds_leakage():
    p=_pmatrix()
    p["protections"]["odds_used_to_generate_probability"]=True
    with pytest.raises(ValueError,match="PMATRIX_ODDS_LEAKAGE"):
        build_audit(
            preregistry=_prereg(),
            cycle=_cycle(),
            p_matrix=p,
            target_date="2026-10-28",
        )


def test_lineage_rejects_post_kickoff_pmatrix_row():
    p=_pmatrix()
    p["rows"][0]["kickoff_utc"]="2026-10-28T04:00:00+00:00"
    with pytest.raises(ValueError,match="PMATRIX_NOT_STRICTLY_PREMATCH"):
        build_audit(
            preregistry=_prereg(),
            cycle=_cycle(),
            p_matrix=p,
            target_date="2026-10-28",
        )
