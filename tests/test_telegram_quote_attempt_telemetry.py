from datetime import datetime,timezone
from pathlib import Path
import pytest

from tools.telegram_quote_attempt_telemetry import build_attempt,append_attempt,load_verified,summarize_run


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
