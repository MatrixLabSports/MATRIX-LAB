from datetime import datetime, timedelta, timezone

import pytest

from tools.matrix_selfhosted_browser_quote_collector import candidate_pipeline_diagnostic


def test_empty_blocker_audit_is_not_equivalent_to_no_canonical_fixtures(tmp_path):
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    day="2026-11-02"
    folder=tmp_path/"evidence"/"api_football"/"daily_prematch_reports"/day/"over25_shadow_ev"
    folder.mkdir(parents=True)
    (folder/"candidate.json").write_text("{}",encoding="utf-8")
    result=candidate_pipeline_diagnostic(
        {"generated_at_utc":now.isoformat(),"records":[]}, now, root=tmp_path
    )
    assert result["status"]=="NO_BLOCKER_ROWS_NOT_PROOF_OF_ZERO_CANONICAL_FIXTURES"
    assert result["audit_blocker_record_count"]==0
    assert result["canonical_source_inventory"][0]["over25_shadow_ev_files"]==1
    assert result["audit_is_not_all_candidate_inventory"] is True
    assert result["real_money"]=="BLOCKED"
    assert result["automatic_wagering"] is False


def test_stale_audit_fails_diagnostic_freshness_without_false_candidate(tmp_path):
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    old=now-timedelta(hours=2)
    result=candidate_pipeline_diagnostic(
        {"generated_at_utc":old.isoformat(),"records":[]},now,root=tmp_path
    )
    assert result["status"]=="AUDIT_TIMESTAMP_UNVERIFIED_OR_STALE"
    assert result["audit_age_seconds"]==7200


def test_unmatched_blocker_rows_distinguished_from_empty_blocker_audit(tmp_path):
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    result=candidate_pipeline_diagnostic(
        {"generated_at_utc":now.isoformat(),"records":[
            {"fixture_id":"verified-fixture","match":"Home vs Away",
             "kickoff":(now+timedelta(minutes=70)).isoformat(),"p_matrix":0.55}
        ]},now,root=tmp_path
    )
    assert result["status"]=="BLOCKER_ROWS_FILTERED_BY_PREMATCH_PROBABILITY_OR_IDENTITY"


def test_rejects_naive_clock(tmp_path):
    with pytest.raises(ValueError,match="TZ_AWARE"):
        candidate_pipeline_diagnostic({"records":[]},datetime(2026,11,3),root=tmp_path)


def test_browser_uses_fresh_governed_intake_when_blocker_rows_are_empty():
    from tools.matrix_selfhosted_browser_quote_collector import candidate_rows
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    c={"fixture_id":"fixture-1","match":"Home vs Away",
       "kickoff":(now+timedelta(minutes=70)).isoformat(),"p_matrix":0.70}
    audit={"generated_at_utc":now.isoformat(),"records":[],
           "browser_prematch_candidate_rows":[c]}
    assert candidate_rows(audit,now)==[c]


def test_stale_canonical_intake_is_not_used_for_quotes():
    from tools.matrix_selfhosted_browser_quote_collector import candidate_rows
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    c={"fixture_id":"fixture-2","match":"Home vs Away",
       "kickoff":(now+timedelta(minutes=70)).isoformat(),"p_matrix":0.70}
    audit={"generated_at_utc":(now-timedelta(hours=1)).isoformat(),"records":[c],
           "browser_prematch_candidate_rows":[c]}
    assert candidate_rows(audit,now)==[]


def test_canonical_intake_does_not_override_kickoff_or_probability_gates():
    from tools.matrix_selfhosted_browser_quote_collector import candidate_rows
    now=datetime(2026,11,3,4,0,tzinfo=timezone.utc)
    payload={"generated_at_utc":now.isoformat(),"records":[],
             "browser_prematch_candidate_rows":[
               {"fixture_id":"expired","match":"Home vs Away",
                "kickoff":(now-timedelta(minutes=1)).isoformat(),"p_matrix":0.85},
               {"fixture_id":"weak","match":"Home vs Away",
                "kickoff":(now+timedelta(minutes=40)).isoformat(),"p_matrix":0.59},
               {"fixture_id":"far","match":"Home vs Away",
                "kickoff":(now+timedelta(minutes=150)).isoformat(),"p_matrix":0.85},
             ]}
    assert candidate_rows(payload,now)==[]
