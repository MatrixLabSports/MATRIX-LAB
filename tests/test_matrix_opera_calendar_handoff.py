"""Cross-browser persisted evidence can corroborate calendar, never market eligibility."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from tools.matrix_opera_calendar_handoff import discover, persist, validate
from tools.matrix_calendar_browser_observations import exact_label
from tools.matrix_football_sofa_fixture_crosscheck import corroborate

DAY = "2026-11-06"
CAPTURED = datetime(2026, 11, 5, 8, 46, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
URL = "https://www.sofascore.com/es/football/match/everton-coventry-city/lsY#id:16363914"
LABEL = "6/11/26 15:00 Everton Everton Coventry City Coventry 1 1.70 X 4.00 2 4.75"


def intake():
    return {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
            "source": "FOOTBALL_DATA_ORG",
            "provider_status": "AUTHENTICATED_FIXTURE_CAPTURE",
            "target_date_bogota": DAY,
            "real_money": "BLOCKED",
            "signal_generation_authorized": False,
            "fixtures": [{
                "source_fixture_id": "560634", "home": "Everton FC",
                "away": "Coventry City FC",
                "kickoff_utc": "2026-11-06T20:00:00+00:00",
            }]}


def source_doc():
    return {"schema": "MATRIX_OPERA_FOOTBALL_CALENDAR_CAPTURE_V1",
            "source": "SOFASCORE",
            "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
            "source_page_url": f"https://www.sofascore.com/es/football/{DAY}",
            "target_date_bogota": DAY,
            "observed_at_utc": CAPTURED.isoformat(),
            "display_timezone": "America/Bogota",
            "capture_method": "OPERA_CONNECTOR_ACCESSIBILITY_LINKS",
            "links": [{"url": URL, "name": LABEL}],
            "record_count": 1,
            "signal_generation_authorized": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED"}


def prepare(tmp_path, doc=None):
    dest = (tmp_path / "evidence" / "browser_capture_inbox" /
            "opera_football" / DAY / "20261105T084600Z.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(source_doc() if doc is None else doc), encoding="utf-8")
    return dest


def test_actual_date_team_and_kickoff_imported_into_existing_strict_contract(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    assert obs["matches"] and obs["matches"][0]["provider_fixture_id"] == "560634"
    assert obs["matches"][0]["sofascore_event_id"] == "16363914"
    assert obs["capture_method"] == "OPERA_CONNECTOR_SHA256_PROVENANCE"
    assert len(obs["source_capture_sha256"]) == 64
    assert report["telegram_signal_authorized"] is False
    out = tmp_path / "evidence" / "football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    assert persist(out, obs, report, DAY) is True
    verified = corroborate(intake(), json.loads(out.read_text(encoding="utf-8")))
    assert verified["matched_count"] == 1
    assert verified["signal_generation_authorized"] is False


def test_reversed_teams_are_not_an_identity_match():
    assert exact_label(LABEL, DAY, "15:00", "everton", "coventry city")
    reversed_label = "6/11/26 15:00 Coventry City Coventry Everton Everton"
    assert not exact_label(reversed_label, DAY, "15:00", "everton", "coventry city")


def test_wrong_date_and_after_kickoff_fail_closed(tmp_path):
    d = source_doc()
    d["links"][0]["name"] = "5/11/26 15:00 Everton Coventry City"
    prepare(tmp_path, d)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    assert obs is None and report["matched_count"] == 0
    # Dated observation may not be backfilled after kickoff.
    d = source_doc()
    d["observed_at_utc"] = "2026-11-06T21:00:00+00:00"
    validate(d, DAY, now=datetime(2026, 11, 6, 22, tzinfo=timezone.utc))
    prepare(tmp_path, d)
    obs, report = discover(tmp_path, intake(), DAY,
                           now=datetime(2026, 11, 6, 22, tzinfo=timezone.utc))
    assert obs is None and report["matched_count"] == 0


def test_reject_stale_future_unsafe_or_mismatched_screenshot_provenance():
    base = source_doc()
    invalid = [
        {"observed_at_utc": (NOW + timedelta(minutes=3)).isoformat()},
        {"observed_at_utc": (NOW - timedelta(hours=25)).isoformat()},
        {"source_page_url": "https://evil.example/football/2026-11-06"},
        {"target_date_bogota": "2026-11-07"},
        {"display_timezone": "Europe/London"},
        {"signal_generation_authorized": True},
        {"real_money": "ENABLED"},
        {"record_count": 4},
    ]
    for changes in invalid:
        with pytest.raises((ValueError, TypeError)):
            validate({**base, **changes}, DAY, now=NOW)


def test_reject_stronger_previous_evidence_overwrite(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    out = tmp_path / "evidence" / "football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    old = {**obs, "capture_method": "CDP_VISIBLE_EXACT_DATE_TIME_TEAMS_EVENT_ID"}
    out.write_text(json.dumps(old), encoding="utf-8")
    assert persist(out, obs, report, DAY) is False
    assert report["status"] == "EXISTING_BROWSER_EVIDENCE_RETAINED"
    assert json.loads(out.read_text(encoding="utf-8"))["capture_method"] == "CDP_VISIBLE_EXACT_DATE_TIME_TEAMS_EVENT_ID"


def test_no_writer_to_canonical_signal_path(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    with pytest.raises(ValueError, match="OUTPUT_FORBIDDEN"):
        persist(tmp_path / "daily_prematch_reports" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json",
                obs, report, DAY)


def test_newer_equal_size_verified_opera_capture_replaces_stale_observation(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    out = tmp_path / "evidence" / "football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    old = {**obs, "observed_at_utc": (CAPTURED - timedelta(hours=3)).isoformat()}
    out.write_text(json.dumps(old), encoding="utf-8")
    assert persist(out, obs, report, DAY) is True
    stored = json.loads(out.read_text(encoding="utf-8"))
    assert stored["observed_at_utc"] == CAPTURED.isoformat()
    assert stored["signal_generation_authorized"] is False


def test_same_time_stronger_direct_browser_evidence_is_retained(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    out = tmp_path / "evidence" / "football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    old = {**obs, "capture_method": "CDP_VISIBLE_EXACT_DATE_TIME_TEAMS_EVENT_ID"}
    out.write_text(json.dumps(old), encoding="utf-8")
    assert persist(out, obs, report, DAY) is False
    assert report["status"] == "EXISTING_BROWSER_EVIDENCE_RETAINED"


def test_older_observation_cannot_replace_a_newer_capture(tmp_path):
    prepare(tmp_path)
    obs, report = discover(tmp_path, intake(), DAY, now=NOW)
    out = tmp_path / "evidence" / "football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    newer = {**obs, "observed_at_utc": (CAPTURED + timedelta(minutes=5)).isoformat()}
    out.write_text(json.dumps(newer), encoding="utf-8")
    assert persist(out, obs, report, DAY) is False
