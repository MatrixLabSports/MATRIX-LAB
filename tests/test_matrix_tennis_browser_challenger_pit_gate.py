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


def test_precut_duplicate_provider_rows_same_original_identity_source_are_safe_for_research():
    from tools.matrix_tennis_browser_challenger_pit_gate import resolve_unique_precut_history
    h={"rows":29,"latest_row_date":20260907,
       "canonical_source_ids":["C0B2"],"canonical_iocs":["ROU"]}
    x={"provider_player_id":"api-tennis:player:972","pre_cut_history":dict(h)}
    y={"provider_player_id":"rapidapi-tennis:player:53726","pre_cut_history":dict(h)}
    p,reason=resolve_unique_precut_history([x,y])
    assert reason=="UNIQUE_PRE_CUT_HISTORICAL_SOURCE"
    assert p["pre_cut_history"]["canonical_source_ids"]==["C0B2"]
    assert p["provider_player_id"]=="api-tennis:player:972"


def test_conflicting_original_history_source_or_country_blocks():
    from tools.matrix_tennis_browser_challenger_pit_gate import resolve_unique_precut_history
    a={"provider_player_id":"a","pre_cut_history":{"rows":29,"latest_row_date":20260907,
       "canonical_source_ids":["C0B2"],"canonical_iocs":["ROU"]}}
    for override in ({"canonical_source_ids":["X999"]},{"canonical_iocs":["USA"]},
                     {"rows":30},{"latest_row_date":20260908}):
        b={"provider_player_id":"b","pre_cut_history":dict(a["pre_cut_history"],**override)}
        p,reason=resolve_unique_precut_history([a,b])
        assert p is None
        assert reason=="CONFLICTING_PRE_CUT_HISTORICAL_AUTHORITIES"


def test_incomplete_historical_duplicate_not_presented_as_independent_confirmation():
    from tools.matrix_tennis_browser_challenger_pit_gate import resolve_unique_precut_history
    a={"provider_player_id":"api-tennis:player:19536",
       "pre_cut_history":{"rows":42,"latest_row_date":20260907,
       "canonical_source_ids":["H09N"],"canonical_iocs":["DEN"]}}
    b={"provider_player_id":"sofascore:player:207089","biographical_candidates":[{"dob":"19980422"}]}
    p,reason=resolve_unique_precut_history([a,b])
    assert p["provider_player_id"]=="api-tennis:player:19536"
    assert reason=="UNIQUE_PRE_CUT_HISTORICAL_SOURCE"
    p,reason=resolve_unique_precut_history([b])
    assert p is None and reason=="PRE_CUT_HISTORY_NOT_FOUND"


def test_original_nov12_source_players_have_only_historical_candidates_not_authorized_models():
    from tools.matrix_tennis_browser_challenger_pit_gate import (normal,
        resolve_unique_precut_history,COUNTRY_IOC)
    import json
    root=Path(__file__).resolve().parents[1]
    details=json.loads((root/"evidence/tennis_calendar_physical/2026-11-12/sofascore_verified_match_details.json").read_bytes())
    assert details["individual_visible_metadata_verified_count"]==6
    hard=json.loads((root/"evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json").read_bytes())
    clay=json.loads((root/"evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/identity/MATRIX_CLAY_IDENTITY_AUTHORITY_LAST.json").read_bytes())
    for event in details["events"]:
        records=hard["records"] if event["surface"]=="Hard" else clay["records"]
        for player in event["players"]:
            matches=[row for row in records if normal(row.get("provider_display_name") or "")==normal(player["name"])]
            p,reason=resolve_unique_precut_history(matches)
            assert p is not None, (player["name"],reason)
            original=p["pre_cut_history"]
            assert original["canonical_iocs"]==[COUNTRY_IOC[player["country"]]]
            assert original["latest_row_date"]<20261112
    assert details["real_money"]=="BLOCKED"
    assert details["telegram_signal_authorized"] is False


def test_source_gate_uses_only_exact_hash_bound_archived_crossmatch(tmp_path,monkeypatch):
    from tools import matrix_tennis_browser_challenger_pit_gate as mod
    from datetime import timezone
    day="2026-11-12"
    original_sha="a"*64
    latest_sha="b"*64
    archive=mod.OUT/day/"archive"/("MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_"+original_sha+".json")
    (tmp_path/archive).parent.mkdir(parents=True)
    (tmp_path/archive).write_text("{}")
    details={"schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
             "target_date_bogota":day,"source_crossmatch_sha256":original_sha,
             "real_money":"BLOCKED","telegram_signal_authorized":False,
             "observed_at_utc":"2026-11-11T13:00:00Z","events":[]}
    cross={"schema":"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1",
           "target_date_bogota":day,"real_money":"BLOCKED",
           "source_event_equivalence_certified":False,"matches":[]}
    authority={"outcomes_used":False,"post_cut_competitive_data_used":False,
               "silent_imputation":False,"real_money":"BLOCKED","records":[]}
    actual_read=mod.read
    def fake_read(root,p):
        if p==mod.CAPTURE_ROOT/day/mod.DETAIL:
            return details,"c"*64
        if p==mod.OUT/day/mod.CROSS:
            return cross,latest_sha
        if p==archive:
            return cross,original_sha
        if str(p) in mod.AUTHORITIES.values():
            return authority,"d"*64
        return actual_read(root,p)
    monkeypatch.setattr(mod,"read",fake_read)
    result=mod.evaluate(tmp_path,day,T("2026-11-11T14:00:00Z"))
    assert result["sealed_historical_source_crossmatch_used"] is True
    assert result["name_crossmatch_sha256"]==original_sha
    assert result["newest_calendar_crossmatch_sha256"]==latest_sha
    assert result["new_hard_holdout_observations"]==0
    assert result["new_clay_holdout_observations"]==0
    assert result["real_money"]=="BLOCKED"
    (tmp_path/archive).unlink()
    import pytest
    with pytest.raises(ValueError,match="TENNIS_DETAIL_CROSSMATCH_SHA256_MISMATCH"):
        mod.evaluate(tmp_path,day,T("2026-11-11T14:00:00Z"))


def test_altered_archived_crossmatch_hash_is_rejected(tmp_path,monkeypatch):
    from tools import matrix_tennis_browser_challenger_pit_gate as mod
    import pytest
    day="2026-11-12"
    declared="a"*64
    archive=mod.OUT/day/"archive"/("MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_"+declared+".json")
    (tmp_path/archive).parent.mkdir(parents=True)
    (tmp_path/archive).write_text("tampered")
    details={"source_crossmatch_sha256":declared}
    def fake_read(root,p):
        if p==mod.CAPTURE_ROOT/day/mod.DETAIL:
            return details,"c"*64
        if p==mod.OUT/day/mod.CROSS:
            return {},"b"*64
        if p==archive:
            return {},"d"*64
        raise AssertionError("unexpected read")
    monkeypatch.setattr(mod,"read",fake_read)
    with pytest.raises(ValueError,match="TENNIS_ARCHIVED_CROSSMATCH_SHA256_TAMPER"):
        mod.evaluate(tmp_path,day,T("2026-11-11T14:00:00Z"))
