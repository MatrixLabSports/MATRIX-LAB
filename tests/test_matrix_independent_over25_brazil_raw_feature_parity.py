"""Offline regression: archived Brazil and independent history never authorizes signals."""
import json
from datetime import datetime, timezone
from pathlib import Path
from tools.matrix_independent_over25_brazil_raw_feature_parity import inspect
from tests.test_matrix_independent_over25_historical_parity import (
    _realistic_pit_payloads, Resp,
)

CUT = "2026-10-26T21:57:33+00:00"


def sources(tmp_path, n=36):
    api, free = _realistic_pit_payloads(n)
    for row in api["response"]:
        row["league"]["id"] = 71
    for row in free["matches"]:
        row["competition"]["id"] = 2013
    archived = tmp_path / "league_71_season_2026.bin"
    archived.write_text(json.dumps(api), encoding="utf-8")
    cycle = tmp_path / "cycle_summary.json"
    cycle.write_text(json.dumps({
        "status": "PASS", "finished_at_utc": CUT,
    }), encoding="utf-8")
    return archived, cycle, free


def test_brazil_equal_historical_raw_features_replay_without_production(tmp_path):
    archived, cycle, free = sources(tmp_path)
    def fake(req, timeout):
        assert "/competitions/BSA/matches" in req.full_url
        assert req.get_header("X-auth-token") == "fake-secret"
        assert timeout == 25
        return Resp(free)
    report = inspect("fake-secret", archive=archived, cycle=cycle, opener=fake)
    assert report["status"] == "PASS_BRAZIL_HISTORICAL_SCORE_CONCORDANCE_ONLY"
    assert report["matched_exact_result_count"] == 36
    raw = report["raw_group_feature_parity"]
    assert raw["source_league"] == 2013
    assert raw["reference_league"] == 71
    assert raw["scoreable_both"] > 0
    assert raw["different_raw_group_feature_or_probability_count"] == 0
    assert raw["same_raw_group_feature_and_probability_count"] == raw["scoreable_both"]
    assert report["original_calibrated_feature_equivalence_verified"] is False
    assert report["canonical_enriched_pit_equivalence_verified"] is False
    assert report["all_six_leagues_equivalence_verified"] is False
    assert report["signal_generation_authorized"] is False
    assert report["telegram_messages_sent"] == 0
    assert report["real_money"] == "BLOCKED"


def test_brazil_historical_result_disagreement_fails_closed(tmp_path):
    archived, cycle, free = sources(tmp_path)
    free["matches"][4]["score"]["fullTime"]["away"] += 2
    report = inspect(
        "fake-secret", archive=archived, cycle=cycle,
        opener=lambda *_args, **_kwargs: Resp(free),
    )
    assert report["score_disagreement_count"] == 1
    assert report["historical_goal_result_concordance_verified"] is False
    assert report["raw_group_feature_parity"][
        "different_raw_group_feature_or_probability_count"] > 0
    assert report["signal_generation_authorized"] is False


def test_brazil_missing_key_never_contacts_free_provider(tmp_path):
    archived, cycle, free = sources(tmp_path)
    def forbid(*_a, **_kw):
        raise AssertionError("NETWORK_FORBIDDEN")
    report = inspect("", archive=archived, cycle=cycle, opener=forbid)
    assert report["status"] == "BLOCKED_MISSING_FREE_PROVIDER_KEY"
    assert report["network_calls"] == 0
    assert report["signal_generation_authorized"] is False


def test_brazil_archive_wrong_league_never_promoted(tmp_path):
    archived, cycle, free = sources(tmp_path)
    d = json.loads(archived.read_text(encoding="utf-8"))
    d["response"][0]["league"]["id"] = 135
    archived.write_text(json.dumps(d), encoding="utf-8")
    report = inspect(
        "fake-secret", archive=archived, cycle=cycle,
        opener=lambda *_a, **_kw: Resp(free),
    )
    assert report["status"] == "BLOCKED_BRAZIL_PARITY_PROBE_ERROR"
    assert report["network_calls"] == 0
    assert report["signal_generation_authorized"] is False
