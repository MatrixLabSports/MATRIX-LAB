"""Exact browser-visible Challenger metadata is separate from model holdout admission."""
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_tennis_browser_challenger_pit_gate import evaluate

ROOT=Path.cwd()
DAY="2026-11-04"
T=lambda s:datetime.fromisoformat(s.replace("Z","+00:00"))

def test_two_real_4_nov_challenger_source_rows_pre_match():
    r=evaluate(ROOT,DAY,T("2026-11-04T16:00:00Z"))
    assert r["source_metadata_verified_before_kickoff"]==2
    assert r["hard_source_metadata_ready"]==1
    assert r["clay_source_metadata_ready"]==1
    assert r["new_hard_holdout_observations"]==0
    assert r["new_clay_holdout_observations"]==0
    assert all(x["official_holdout_admitted"] is False for x in r["events"])
    assert all(x["model_probability_computed"] is False for x in r["events"])
    assert r["real_money"]=="BLOCKED"
    hist={x["surface"]:x["historical_players_found"] for x in r["events"]}
    assert hist=={"Hard":2,"Clay":1}

def test_old_calendar_cannot_backdate_new_prematch_admission():
    r=evaluate(ROOT,DAY,T("2026-11-04T20:00:00Z"))
    assert r["source_metadata_verified_before_kickoff"]==0
    assert all("PROSPECTIVE_SCORE_WINDOW_CLOSED" in x["blocked"] for x in r["events"])
    assert r["new_hard_holdout_observations"]==0
    assert r["new_clay_holdout_observations"]==0


def test_calendar_utc_token_seconds_match_verified_kickoff():
    """Regression: source tokens include HHMMSS, not only HHMM."""
    from datetime import datetime, timezone
    raw = "20261104T172500Z"
    parsed = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    assert parsed == T("2026-11-04T17:25:00Z")


def test_bogota_evening_match_date_survives_utc_day_rollover():
    from tools.matrix_tennis_browser_challenger_pit_gate import kickoff_in_bogota_calendar_day
    evening=T("2026-11-07T02:00:00Z")
    assert kickoff_in_bogota_calendar_day(evening,"2026-11-06") is True
    assert kickoff_in_bogota_calendar_day(evening,"2026-11-07") is False


def test_never_accept_utc_without_timezone_for_local_calendar():
    import pytest
    from tools.matrix_tennis_browser_challenger_pit_gate import kickoff_in_bogota_calendar_day
    with pytest.raises(ValueError,match="KICKOFF_TIMEZONE_REQUIRED"):
        kickoff_in_bogota_calendar_day(datetime(2026,11,6,21),"2026-11-06")

def test_real_nov6_cross_provider_clock_conflict_blocks_hard_only():
    r=evaluate(ROOT,"2026-11-06",T("2026-11-06T02:00:00Z"))
    assert r["cross_provider_fixture_start_display_conflict_count"]==1
    assert r["hard_source_metadata_ready"]==0
    assert r["clay_source_metadata_ready"]==1
    by_id={x["sofascore_id"]:x for x in r["events"]}
    assert "TWO_PROVIDER_FIXTURE_START_DISPLAY_CONFLICT" in by_id["17427360"]["blocked"]
    assert by_id["17427540"]["source_two_provider_fixture_clock_display_agrees"] is True
    assert by_id["17427540"]["source_profile_biographical_triplet_research_verified"] is True
    assert r["new_hard_holdout_observations"]==r["new_clay_holdout_observations"]==0


def test_biographical_clock_sha_drift_rejected(monkeypatch):
    from copy import deepcopy
    from tools import matrix_tennis_browser_challenger_pit_gate as mod
    before=mod.read
    def altered(root,p):
        doc,h=before(root,p)
        if str(p).endswith("MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST.json"):
            doc=deepcopy(doc)
            doc["source_sha256"]["prematch_details"]="bad-source-digest"
        return doc,h
    monkeypatch.setattr(mod,"read",altered)
    import pytest
    with pytest.raises(ValueError,match="TENNIS_BIOGRAPHY_CLOCK_RESEARCH_SOURCE_DRIFT"):
        mod.evaluate(ROOT,"2026-11-06",T("2026-11-06T02:00:00Z"))
