"""Synthetic defensive checks for exact source-provider event-time drift receipts."""
import hashlib
import json
from copy import deepcopy

from tools.matrix_13_rescheduled_period_receipt_attestation import (
    verify_original_event_time_drift,
)

FID = "123"


def facts():
    immutable = {
        "fixture_id": FID,
        "kickoff_utc": "2026-10-25T19:00:00Z",
        "freeze_at_utc": "2026-10-23T12:00:00Z",
        "home_team_id": "10",
        "away_team_id": "20",
        "input_sha256": "b"*64,
    }
    receipt = {
        "fixture_id": FID,
        "kickoff_utc": "2026-10-25T19:00:00Z",
        "freeze_at_utc": "2026-10-23T12:00:00Z",
        "settled_at_utc": "2026-10-25T23:30:00Z",
        "terminal_status": "FT",
        "result_source_provider": "api_football",
        "fulltime_home_goals": 2,
        "fulltime_away_goals": 1,
    }
    source = {
        "errors": [], "results": 1,
        "response": [{
            "fixture": {
                "id": 123, "date": "2026-10-25T20:00:00Z",
                "status": {"short": "FT"},
            },
            "teams": {"home": {"id": 10}, "away": {"id": 20}},
            "score": {
                "halftime": {"home": 1, "away": 0},
                "fulltime": {"home": 2, "away": 1},
            },
            "goals": {"home": 2, "away": 1},
        }],
    }
    return immutable, receipt, source


def check(tmp_path, immutable=None, receipt=None, source=None):
    a,b,c = facts()
    a = immutable or a
    b = receipt or b
    c = source or c
    raw=json.dumps(c,sort_keys=True).encode()
    (tmp_path/"fixture_123.bin").write_bytes(raw)
    b["result_payload_sha256"]=hashlib.sha256(raw).hexdigest()
    return verify_original_event_time_drift(FID,a,b,tmp_path)


def test_hash_bound_rescheduled_candidate_stays_research_only(tmp_path):
    r=check(tmp_path)
    assert r["status"]=="RESEARCH_ATTESTATION_NOT_ADMITTED_TO_CALIBRATION"
    assert r["source_minus_frozen_start_minutes"]==60
    assert r["prediction_frozen_before_both_kickoffs"] is True
    assert r["original_explicit_halftime_goals"]=={"home":1,"away":0}
    assert r["cross_provider_event_time_confirmed"] is False
    assert r["formal_period_cohort_admission"] is False


def test_no_halftime_does_not_impute_from_final(tmp_path):
    a,b,c=facts()
    c["response"][0]["score"]["halftime"]["home"]=None
    r=check(tmp_path,a,b,c)
    assert r["status"]=="NOT_ADMITTED"
    assert r["blocker"]=="EXPLICIT_HALFTIME_OR_FINAL_SCORE_MISSING_OR_INVALID"


def test_source_team_swap_fails_without_string_fuzzy_join(tmp_path):
    a,b,c=facts()
    c["response"][0]["teams"]["home"]["id"]=20
    r=check(tmp_path,a,b,c)
    assert r["status"]=="NOT_ADMITTED"
    assert r["blocker"]=="SOURCE_TEAMS_NOT_FROZEN_IDENTITY"


def test_snapshot_frozen_after_actual_start_is_rejected(tmp_path):
    a,b,c=facts()
    a["kickoff_utc"]="2026-10-25T21:00:00Z"
    b["kickoff_utc"]="2026-10-25T21:00:00Z"
    a["freeze_at_utc"]="2026-10-25T19:30:00Z"
    b["freeze_at_utc"]="2026-10-25T19:30:00Z"
    c["response"][0]["fixture"]["date"]="2026-10-25T18:00:00Z"
    r=check(tmp_path,a,b,c)
    assert r["status"]=="NOT_ADMITTED"
    assert r["blocker"]=="FORECAST_NOT_BEFORE_BOTH_STARTS_OR_SETTLED_PRESTART"


def test_fake_source_identity_or_final_goals_is_not_admitted(tmp_path):
    a,b,c=facts()
    c["response"][0]["fixture"]["id"]=777
    assert check(tmp_path,a,b,c)["blocker"]=="SOURCE_FIXTURE_ID_OR_STANDARD_STATUS_MISMATCH"
    a,b,c=facts()
    c["response"][0]["score"]["fulltime"]["home"]=4
    assert check(tmp_path,a,b,c)["blocker"]=="FINAL_SCORE_NOT_EQUAL_TO_ORIGINAL_HASHCHAIN"


def test_no_schedule_change_no_exception(tmp_path):
    a,b,c=facts()
    c["response"][0]["fixture"]["date"]=a["kickoff_utc"]
    r=check(tmp_path,a,b,c)
    assert r["status"]=="NOT_ADMITTED"
    assert r["blocker"]=="NOT_AN_EVENT_TIME_DRIFT"


def test_original_freeze_identity_mismatch_never_repaired(tmp_path):
    a,b,c=facts()
    a["kickoff_utc"]="2026-10-25T19:30:00Z"
    r=check(tmp_path,a,b,c)
    assert r["blocker"]=="ORIGINAL_PREMATCH_LINEAGE_CONFLICT"
