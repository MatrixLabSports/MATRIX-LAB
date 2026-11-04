from datetime import datetime, timezone, timedelta
from tools.matrix_independent_enriched_gap_feasibility import evaluate_free_matches
import pytest

ASOF="2026-11-03T18:00:00Z"
TARGET="2026-11-04T18:00:00Z"

def event(ident,home="10",away="20",updated="2026-11-02T22:00:00Z",
          kickoff="2026-11-02T20:00:00Z",status="FINISHED",hg=2,ag=1):
    return {"id":ident,"utcDate":kickoff,"lastUpdated":updated,"status":status,
       "homeTeam":{"id":int(home)},"awayTeam":{"id":int(away)},
       "score":{"fullTime":{"home":hg,"away":ag}}}

def run(rows):
    return evaluate_free_matches({"matches":rows},home_id="10",away_id="20",
       as_of_utc=ASOF,target_kickoff_utc=TARGET)

def test_free_history_feasibility_is_not_model_parity():
    rows=[event(i,kickoff=f"2026-11-0{i}T20:00:00Z") for i in range(1,6)]
    result=run(rows)
    assert result["workstreams"]["home_history"]["minimum_count_met"] is True
    assert result["workstreams"]["away_history"]["minimum_count_met"] is True
    assert result["workstreams"]["prematch_lineage"]["original_api_football_enriched_pit_parity_verified"] is False
    assert result["p_matrix"] is None
    assert result["telegram_signal_authorized"] is False

def test_reject_data_revised_after_freeze():
    r=run([event(1,updated="2026-11-04T10:00:00Z")])
    assert r["workstreams"]["home_history"]["observed_eligible_count"]==0
    assert r["rejections"]["updated_after_freeze"]==1

def test_reject_future_results_even_if_marked_finished():
    r=run([event(1,kickoff="2026-11-03T20:00:00Z")])
    assert r["rejections"]["not_finished_before_freeze"]==1

def test_reject_missing_update_timestamp():
    r=run([event(1,updated=None)])
    assert r["rejections"]["missing_last_updated"]==1

def test_reject_missing_scores():
    r=run([event(1,hg=None)])
    assert r["rejections"]["invalid_score"]==1

def test_deduplicates_provider_match_id():
    r=run([event(1),event(1)])
    assert r["workstreams"]["home_history"]["observed_eligible_count"]==1

def test_reject_non_prematch_analysis():
    with pytest.raises(ValueError,match="NOT_BEFORE_KICKOFF"):
        evaluate_free_matches({"matches":[]},home_id="10",away_id="20",
           as_of_utc=TARGET,target_kickoff_utc=TARGET)

def test_never_claim_three_specific_feature_diffs_without_rowwise_diff():
    r=run([])
    assert r["the_three_workstreams_are_not_claimed_as_three_unmatched_features"] is True
    assert r["eleven_feature_diff_present"] is False
