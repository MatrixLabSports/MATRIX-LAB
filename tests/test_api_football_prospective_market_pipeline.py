from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_market_freeze import build_freeze, merge_incremental_freeze
from tools.api_football_prospective_market_settlement import settle
from tools.api_football_prediction_store import load_chunked_json


def test_prospective_freeze_is_future_unseen_and_holdout_safe():
    d=build_freeze(Path("."),datetime.now(timezone.utc))
    # A healthy run can legitimately have zero newly eligible future fixtures.
    # Safety invariants below are the contract; wall-clock inventory is not.
    assert d["frozen_event_count"] >= 0
    assert d["protections"]["future_only"] is True
    assert d["protections"]["unseen_events_only"] is True
    assert d["protections"]["original_357_holdout_excluded"] is True
    assert d["protections"]["outcomes_read_at_freeze"] is False
    assert d["protections"]["missing_feature_imputation"] is False
    assert d["protections"]["p_matrix_generated"] is False
    assert d["protections"]["real_money"]=="BLOCKED"
    forbidden=set(__import__("json").loads(Path("evidence/api_football/btts_challenger_v2/exclusion_registry.json").read_text())["forbidden_fixture_ids"])
    seen=set(str(r["fixture_id"]) for r in load_chunked_json(Path("evidence/api_football/model_validation/retrospective_predictions_manifest.json"))["rows"])
    for row in d["rows"]:
        assert str(row["fixture_id"]) not in forbidden
        assert str(row["fixture_id"]) not in seen
        assert row["outcome"] is None
        assert row["settlement_status"]=="PENDING_FINAL"
        assert datetime.fromisoformat(row["freeze_at_utc"]) < datetime.fromisoformat(row["kickoff_utc"])


def test_settlement_never_marks_nonfinal_as_final():
    root=Path(".")
    d=settle(root)
    assert d["settlement_summary"]["settlement_final_only"] is True
    assert d["settlement_summary"]["nonfinal_outcomes_read"] is False
    for row in d["rows"]:
        if row["settlement_status"]!="FINAL":
            assert row["outcome"] is None


def _freeze_row(fid:str, freeze_at:str, kickoff:str):
    return {
        "fixture_id":fid,
        "target_key":f"api_football:fixture:{fid}",
        "competition_id":"39",
        "competition_name":"League",
        "home_team_id":"40",
        "home_team_name":"Home",
        "away_team_id":"41",
        "away_team_name":"Away",
        "season":2026,
        "kickoff_utc":kickoff,
        "freeze_at_utc":freeze_at,
        "input_sha256":"a"*64,
        "historical_baseline_source":"evidence/test.bin",
        "historical_baseline_sample_size":20,
        "poisson_reference":{"1x2":{"H":0.5,"D":0.25,"A":0.25},"over_2_5":0.5,"btts":0.5},
        "frozen_research_probabilities":{"1x2":{"H":0.55,"D":0.25,"A":0.20},"over_2_5":0.52,"btts_v2":0.51},
        "market_status":{"1x2":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW","over_2_5":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW","btts_v2":"NEW_PROSPECTIVE_HOLDOUT"},
        "outcome":None,
        "settlement_status":"PENDING_FINAL",
        "odds_used_to_generate_probability":False,
        "p_matrix":None,
    }


def _freeze_doc(rows, created="2026-09-28T10:00:00+00:00"):
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_MARKET_FREEZE_V1",
        "created_at_utc":created,
        "source_canonical_bundle_sha256":"b"*64,
        "source_market_governance_holdout_sha256":"c"*64,
        "source_btts_v2_exclusion_registry_sha256":"d"*64,
        "historical_seen_fixture_count":10,
        "permanently_forbidden_original_holdout_count":357,
        "frozen_event_count":len(rows),
        "excluded_event_count":0,
        "rows":rows,
        "exclusions":[],
        "protections":{
            "future_only":True,
            "unseen_events_only":True,
            "freeze_strictly_before_kickoff":True,
            "original_357_holdout_excluded":True,
            "missing_feature_imputation":False,
            "outcomes_read_at_freeze":False,
            "settlement_final_only":True,
            "odds_used_to_generate_probability":False,
            "p_matrix_generated":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def test_incremental_freeze_appends_new_fixture_without_mutating_existing():
    old_row=_freeze_row("100","2026-09-28T10:00:00+00:00","2026-09-29T10:00:00+00:00")
    existing=_freeze_doc([old_row])
    new_row=_freeze_row("101","2026-09-28T12:00:00+00:00","2026-09-30T10:00:00+00:00")
    candidate=_freeze_doc([old_row,new_row],created="2026-09-28T12:00:00+00:00")

    merged,summary=merge_incremental_freeze(existing=existing,candidate=candidate)

    assert summary["status"]=="APPENDED"
    assert summary["previous_event_count"]==1
    assert summary["new_event_count"]==1
    assert summary["new_fixture_ids"]==["101"]
    assert summary["cumulative_event_count"]==2
    assert summary["existing_rows_unchanged"] is True
    by_id={row["fixture_id"]:row for row in merged["rows"]}
    assert by_id["100"]==old_row
    assert by_id["101"]==new_row
    assert merged["frozen_event_count"]==2
    assert merged["incremental_mode"] is True


def test_incremental_freeze_is_idempotent_when_only_existing_fixture_is_seen():
    old_row=_freeze_row("100","2026-09-28T10:00:00+00:00","2026-09-29T10:00:00+00:00")
    existing=_freeze_doc([old_row])
    candidate=_freeze_doc([dict(old_row)],created="2026-09-28T12:00:00+00:00")

    merged,summary=merge_incremental_freeze(existing=existing,candidate=candidate)

    assert summary["status"]=="NO_NEW_ELIGIBLE_EVENTS"
    assert summary["new_event_count"]==0
    assert summary["cumulative_event_count"]==1
    assert merged["rows"]==[old_row]


def test_incremental_freeze_rejects_post_start_new_row():
    existing=_freeze_doc([])
    bad=_freeze_row("101","2026-09-30T10:00:00+00:00","2026-09-30T09:59:00+00:00")
    candidate=_freeze_doc([bad],created="2026-09-30T10:00:00+00:00")
    try:
        merge_incremental_freeze(existing=existing,candidate=candidate)
    except ValueError as exc:
        assert "INCREMENTAL_FREEZE_NOT_PREMATCH" in str(exc)
    else:
        raise AssertionError("post-start incremental freeze must fail")


def test_incremental_freeze_blocks_same_physical_match_with_new_fixture_id():
    old=_freeze_row("100","2026-09-28T10:00:00+00:00","2026-09-29T10:00:00+00:00")
    existing=_freeze_doc([old])
    alias=_freeze_row("999","2026-09-28T12:00:00+00:00","2026-09-29T10:00:00+00:00")
    candidate=_freeze_doc([alias],created="2026-09-28T12:00:00+00:00")

    merged,summary=merge_incremental_freeze(existing=existing,candidate=candidate)

    assert summary["new_event_count"]==0
    assert summary["physical_collision_blocked_count"]==1
    assert summary["physical_duplicate_collisions"][0]["fixture_id"]=="999"
    assert merged["frozen_event_count"]==1


def test_incremental_freeze_blocks_suspicious_same_pair_within_36h():
    old=_freeze_row("100","2026-09-28T10:00:00+00:00","2026-09-29T10:00:00+00:00")
    existing=_freeze_doc([old])
    alias=_freeze_row("999","2026-09-28T12:00:00+00:00","2026-09-30T20:00:00+00:00")
    candidate=_freeze_doc([alias],created="2026-09-28T12:00:00+00:00")

    merged,summary=merge_incremental_freeze(existing=existing,candidate=candidate)

    assert summary["new_event_count"]==0
    assert summary["physical_collision_blocked_count"]==1
    assert summary["suspicious_physical_collisions"][0]["fixture_id"]=="999"
    assert merged["frozen_event_count"]==1
