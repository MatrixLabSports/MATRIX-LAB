"""Independent synthetic controls for cumulative ESPN research settlement."""
from datetime import datetime, timezone, timedelta
from copy import deepcopy
import pytest
from tools.matrix_espn_all_cohorts_cumulative_oos import score_all


NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)
T0 = "2026-11-22T04:51:41+00:00"
K1 = "2026-11-22T11:30:00+00:00"
K2 = "2026-11-22T14:00:00+00:00"


def row(fid, league="135", kickoff=K1, p=.57):
    return {
        "provider_fixture_id": fid,
        "original_league_id_research_only": league,
        "research_frozen_at_utc": T0,
        "target_source_received_at_utc": "2026-11-22T04:48:00+00:00",
        "kickoff_utc": kickoff,
        "home_provider_team_id": "109",
        "away_provider_team_id": "454",
        "research_probability_over25": p,
        "source_history_feature_trace": {
            "poisson_over25": .52,
            "group_baseline_over25": .47,
        },
    }


def cohort(name, entries):
    return {
        "archive_name": name,
        "archive_sha256": "0" * 64 if name == "base" else "1" * 64,
        "prospective_count": len(entries),
        "research_rows": entries,
    }


def final(fid, kickoff=K1, hg=2, ag=1):
    return {
        "id": fid, "league": "135", "kickoff": datetime.fromisoformat(kickoff),
        "home": "109", "away": "454",
        "goals": (hg,ag),
        "received": datetime(2026,11,22,18,tzinfo=timezone.utc),
        "raw_sha256": "f" * 64,
    }


def test_two_distinct_archives_are_both_settled_without_overwriting():
    a=[cohort("base",[row("1")]),cohort("rolling",[row("2",kickoff=K2,p=.45)])]
    out=score_all(a,{"1":final("1"),"2":final("2",kickoff=K2,hg=1,ag=0)},now=NOW)
    assert out["immutable_cohort_archives_verified"]==2
    assert out["distinct_frozen_research_probabilities"]==2
    assert out["prospectively_settled"]==2
    assert out["awaiting_authentic_final"]==0
    assert out["per_league"]["135"]["settled"]==2
    assert out["settled"][0]["cohort_archive_sha256"]=="0"*64
    assert out["settled"][1]["cohort_archive_sha256"]=="1"*64
    assert out["overall_model_brier"]==pytest.approx((.43**2+.45**2)/2)
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False


def test_missing_final_is_not_loss_or_fake_settlement():
    out=score_all([cohort("base",[row("1")])],{},now=NOW)
    assert out["prospectively_settled"]==0
    assert out["awaiting_authentic_final"]==1
    assert out["overall_model_brier"] is None


def test_duplicate_provider_event_across_cohorts_rejected():
    a=[cohort("base",[row("1")]),cohort("rolling",[row("1")])]
    with pytest.raises(ValueError,match="FROZEN_EVENT_SCORED_TWICE"):
        score_all(a,{},now=NOW)


def test_wrong_provider_team_identity_rejected_never_settled():
    bad=final("1");bad["away"]="different-team-id"
    out=score_all([cohort("base",[row("1")])],{"1":bad},now=NOW)
    assert out["prospectively_settled"]==0
    assert out["rejected_identity_or_temporal_provenance"]==1


def test_final_receipt_before_match_is_rejected():
    bad=final("1")
    bad["received"]=datetime(2026,11,22,9,tzinfo=timezone.utc)
    out=score_all([cohort("base",[row("1")])],{"1":bad},now=NOW)
    assert out["prospectively_settled"]==0
    assert out["rejected_identity_or_temporal_provenance"]==1


def test_future_event_not_settled_even_if_score_is_supplied():
    far="2026-11-24T11:30:00+00:00"
    x=score_all([cohort("base",[row("1",kickoff=far)])],
                {"1":final("1",kickoff=far)},now=NOW)
    assert x["prospectively_settled"]==0
    assert x["awaiting_authentic_final"]==1


def test_research_source_observed_after_freeze_cannot_count():
    x=row("1")
    x["target_source_received_at_utc"]="2026-11-22T04:52:00Z"
    with pytest.raises(ValueError,match="ORIGINAL_PREGAME_RECEIPT_INVALID"):
        score_all([cohort("base",[x])],{},now=NOW)


def test_probability_from_original_freeze_must_be_real():
    x=row("1",p=1.4)
    with pytest.raises(ValueError,match="FROZEN_PROBABILITY_OR_BENCHMARK_INVALID"):
        score_all([cohort("base",[x])],{},now=NOW)


def test_declared_cohort_count_conservation():
    x=cohort("base",[row("1")]);x["prospective_count"]=2
    with pytest.raises(ValueError,match="CUMULATIVE_COHORT_CONSERVATION_FAILED"):
        score_all([x],{},now=NOW)
