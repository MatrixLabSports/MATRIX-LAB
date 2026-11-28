"""Team-venue Bayesian V2 only uses historical results, not target labels.

Any data generated in these mathematical tests is synthetic and does not
become a verified research observation or calibrated MATRIX cohort.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import matrix_hybrid_team_venue_beta_v2 as v2

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json"
PREMATCH = datetime(2026, 11, 20, 0, tzinfo=timezone.utc)


def manifest():
    return json.loads(MANIFEST.read_bytes())


def test_beta_team_role_probability_is_not_constant_when_teams_differ():
    a = v2.p_team_venue(
        league_games=100, league_over=50,
        home_games=10, home_over=9, away_games=10, away_over=8)
    b = v2.p_team_venue(
        league_games=100, league_over=50,
        home_games=10, home_over=1, away_games=10, away_over=2)
    assert 0 < b["p_over25"] < 0.5 < a["p_over25"] < 1
    assert a["league_prior_p"] == b["league_prior_p"] == 0.5


def test_bayesian_role_minimums_block_insufficient_team_history():
    with pytest.raises(ValueError, match="INSUFFICIENT_PREMATCH_TEAM_OR_LEAGUE_HISTORY"):
        v2.p_team_venue(league_games=100, league_over=50,
                       home_games=2, home_over=1,
                       away_games=10, away_over=5)


def test_no_future_score_can_be_added_after_kickoff(tmp_path):
    result = v2.run(tmp_path, manifest(),
        datetime(2026, 11, 22, 23, tzinfo=timezone.utc))
    assert result["new_forecast_count"] == 0
    assert result["expired_unfrozen_count"] == 37
    assert result["automatic_model_promotion"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"] == "BLOCKED"


def test_physical_authentic_37_fixture_cohort_produces_personalized_research():
    report = v2.run(ROOT, manifest(), PREMATCH)
    assert report["blocked_count"] == 0, report["blocked"]
    assert (report["new_forecast_count"] +
            report["existing_forecast_count"] == 37)
    assert all(row["target_future_result_used"] is False
               for row in report["scored"])
    assert all(row["original_official_p_matrix_certified"] is False
               for row in report["scored"])
    assert all(row["forecast_frozen_at_utc"] < row["event_start_at_utc"]
               for row in report["scored"])
    assert report["scientific_improvement_certified"] is False
    assert report["original_parameters_mutated"] is False
    assert report["real_money"] == "BLOCKED"


def test_real_canonical_source_sha_tamper_fails_closed():
    doc = manifest()
    doc["prelabel_research_pairs"] = doc["prelabel_research_pairs"][:1]
    doc["recovered_research_pair_count"] = 1
    doc["prelabel_research_pairs"][0]["common_history_raw_sha256"] = "0"*64
    report = v2.run(ROOT, doc, PREMATCH)
    assert report["new_forecast_count"] == 0
    assert report["blocked_count"] == 1
    assert report["real_money"] == "BLOCKED"


def test_output_is_preregistered_and_has_distinct_model_id():
    doc = manifest()
    item = doc["prelabel_research_pairs"][0]
    report = v2.run(ROOT, {
        **doc,
        "prelabel_research_pairs": [item],
        "recovered_research_pair_count": 1
    }, PREMATCH)
    if report["scored"]:
        p = report["scored"][0]
        assert p["model_id"] == "MATRIX_HYBRID_TEAM_VENUE_BETA_V2"
        assert p["policy_fixed_before_observing_future_result"]["team_prior_matches"] == 6.0
        assert p["source_historical_payload_sha256"] == item["common_history_raw_sha256"]
        assert p["source_poisson_research_freeze_sha256"] == item["poisson_freeze_sha256"]
    assert report["blocked_count"] == 0, report["blocked"]
