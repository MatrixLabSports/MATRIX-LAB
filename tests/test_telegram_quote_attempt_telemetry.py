from datetime import datetime,timezone
from pathlib import Path
import pytest

from tools.telegram_quote_attempt_telemetry import build_attempt,append_attempt,load_verified,summarize_run,summarize_cumulative


def _diag():
    return {
      "status":"NO_EXACT_OVER25_FOUND",
      "identity_top_scores":[0.97],
      "identity_top_candidates":[{"score":0.97,"event_id":"ev1"}],
      "odds_api_event_id":"ev1",
      "rows_by_book":{"betano":3,"betplay":2,"rushbet":1},
      "candidate_lines_by_book":{
        "betano":[{"market_key":"total","side":"over","line":2.25,"odds":1.8},{"market_key":"total","side":"over","line":2.75,"odds":2.0}],
        "betplay":[{"market_key":"total","side":"over","line":2.5,"odds":1.9}],
        "rushbet":[],
      }
    }


def test_attempt_captures_identity_books_nearby_lines_and_exact_odds():
    row=build_attempt(
      fixture_id="10",signal_key="k",query_at_utc=datetime(2026,10,26,1,0,tzinfo=timezone.utc),
      kickoff="2026-10-26T01:30:00+00:00",odds_diag=_diag(),api_diag={"status":"X"},
      selected_offer={"house":"BetPlay","odds":1.9},final_discard_reason="PASS_FINAL_PREMATCH_REVALIDATION",run_token="r1")
    assert row["seconds_to_kickoff"]==1800
    assert row["identity_match"]["state"]=="MATCHED"
    assert row["houses"]["betano"]["nearby_lines_2_25_2_75"]==[2.25,2.75]
    assert row["houses"]["betplay"]["over_2_5_seen"] is True
    assert row["houses"]["betplay"]["exact_over_2_5_odds"]==[1.9]


def test_append_only_hash_chain_rejects_duplicate_attempt(tmp_path:Path):
    path=tmp_path/"attempts.jsonl"
    row=build_attempt(
      fixture_id="10",signal_key="k",query_at_utc=datetime(2026,10,26,1,0,tzinfo=timezone.utc),
      kickoff="2026-10-26T01:30:00+00:00",odds_diag=_diag(),api_diag={},
      selected_offer=None,final_discard_reason="BLOCKED",run_token="r1")
    append_attempt(path,row)
    assert len(load_verified(path))==1
    with pytest.raises(ValueError,match="QUOTE_ATTEMPT_ALREADY_PERSISTED"):
        append_attempt(path,row)


def test_summary_is_run_scoped_not_historical(tmp_path:Path):
    path=tmp_path/"attempts.jsonl"
    for token,minute in (("old",0),("new",1)):
      row=build_attempt(
        fixture_id=token,signal_key=token,query_at_utc=datetime(2026,10,26,1,minute,tzinfo=timezone.utc),
        kickoff="2026-10-26T02:00:00+00:00",odds_diag=_diag(),api_diag={},
        selected_offer=None,final_discard_reason="BLOCKED",run_token=token)
      append_attempt(path,row)
    s=summarize_run(load_verified(path),"new")
    assert s["quote_attempts_live_this_run"]==1
    assert s["exact_over25_coverage_by_house"]["betplay"]==1


def test_cumulative_summary_detects_real_timing_disappearance(tmp_path:Path):
    path=tmp_path/"attempts.jsonl"
    early_diag=_diag()
    late_diag=_diag()
    late_diag["candidate_lines_by_book"]={
      "betano":[{"market_key":"total","side":"over","line":2.25,"odds":1.8}],
      "betplay":[],
      "rushbet":[],
    }
    for minute,diag in ((0,early_diag),(20,late_diag)):
      row=build_attempt(
        fixture_id="timing1",signal_key=f"k{minute}",
        query_at_utc=datetime(2026,10,26,1,minute,tzinfo=timezone.utc),
        kickoff="2026-10-26T01:30:00+00:00",odds_diag=diag,api_diag={},
        selected_offer=None,final_discard_reason="BLOCKED",run_token=f"r{minute}")
      append_attempt(path,row)
    s=summarize_cumulative(load_verified(path))
    assert s["real_quote_attempts_total"]==2
    assert s["timing_disappearance_fixture_count"]==1
    assert s["timing_disappearance_fixtures"][0]["fixture_id"]=="timing1"
    assert s["synthetic_attempts_included"] is False


def test_cumulative_sample_gate_requires_50_real_attempts(tmp_path:Path):
    path=tmp_path/"attempts.jsonl"
    for i in range(3):
      row=build_attempt(
        fixture_id=str(i),signal_key=str(i),
        query_at_utc=datetime(2026,10,26,1,i,tzinfo=timezone.utc),
        kickoff="2026-10-26T03:00:00+00:00",odds_diag=_diag(),api_diag={},
        selected_offer=None,final_discard_reason="BLOCKED",run_token=str(i))
      append_attempt(path,row)
    s=summarize_cumulative(load_verified(path))
    assert s["sample_gate_status"]=="ACCUMULATING_REAL_REVALIDATIONS"
    assert s["remaining_to_minimum"]==47



def test_api_football_house_evidence_is_merged_into_immutable_view():
    row=build_attempt(
      fixture_id="11",signal_key="k2",query_at_utc=datetime(2026,10,26,1,0,tzinfo=timezone.utc),
      kickoff="2026-10-26T01:30:00+00:00",
      odds_diag={
        "status":"BLOCKED_EVENT_NOT_COVERED",
        "identity_top_scores":[],
        "identity_top_candidates":[],
        "rows_by_book":{},
        "candidate_lines_by_book":{},
      },
      api_diag={
        "status":"PASS_EXACT_AUTHORIZED_OVER25_FOUND",
        "required_house_key":"betano",
        "authorized_books_seen":["betano"],
        "goals_over_under_books":["betano"],
        "over25_books":["betano"],
        "exact_over25_odds_by_book":{"betano":[1.62]},
      },
      selected_offer={"house":"Betano","odds":1.62},
      final_discard_reason="BLOCKED_NO_FRESH_PINNACLE_REFERENCE",
      run_token="r2",
    )
    assert row["houses"]["betano"]["seen"] is True
    assert row["houses"]["betano"]["totals_market_seen"] is True
    assert row["houses"]["betano"]["over_2_5_seen"] is True
    assert row["houses"]["betano"]["available_lines"]==[2.5]
    assert row["houses"]["betano"]["exact_over_2_5_odds"]==[1.62]
    assert row["houses"]["betplay"]["seen"] is False
    assert row["houses"]["rushbet"]["seen"] is False
