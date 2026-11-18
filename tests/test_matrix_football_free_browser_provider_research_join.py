"""Offline anti-promotion tests for authentic-browser/free-provider research join."""
from datetime import datetime
import hashlib
import json
import sys
from pathlib import Path
import pytest

from tools.matrix_football_free_browser_provider_research_join import join

SHA="a"*64

def browser(day="2026-11-18"):
    return {
        "schema":"MATRIX_AUTHORIZED_FOOTBALL_DUAL_BROWSER_RESEARCH_LINKS_V1",
        "status":"RESEARCH_TWO_SOURCE_CANDIDATES_ONLY_NOT_CALENDAR_CERTIFIED",
        "real_money":"BLOCKED",
        "canonical_prematch_inputs_authorized":False,
        "production_p_matrix_authorized":False,
        "target_date_bogota":day,
        "source_capture_at_utc":{
            "sofascore":"2026-11-18T02:23:00+00:00",
            "flashscore":"2026-11-18T02:23:02+00:00",
        },
        "research_candidates":[{
            "home_normalized":"coritiba","away_normalized":"santos",
            "sofascore_event_id":"15235658","flashscore_mid":"nFe3yH7c",
            "sofascore_visible_clock_unverified_timezone":"17:30",
            "cross_provider_identity_certified":False,
        }],
    }

def intake(day="2026-11-18"):
    return {
        "schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "source":"FOOTBALL_DATA_ORG",
        "real_money":"BLOCKED",
        "signal_generation_authorized":False,
        "target_date_bogota":day,
        "generated_at_utc":"2026-11-18T04:25:15+00:00",
        "fixtures":[{
            "home":"Coritiba FBC","away":"Santos FC",
            "source_fixture_id":"555081",
            "league":"Campeonato Brasileiro Série A",
            "kickoff_utc":"2026-11-18T22:30:00+00:00",
            "signal_generation_authorized":False,
        }],
    }

def run(b=None,i=None):
    return join(b or browser(),i or intake(),browser_sha256=SHA,intake_sha256=SHA)

def test_real_nov18_names_are_only_three_source_research_hints():
    d=run()
    assert d["unique_provider_name_pair_matches"]==1
    assert d["prematch_three_source_name_clock_hints"]==1
    assert d["rows"][0]["provider_fixture_id_name_match_only"]=="555081"
    assert d["rows"][0]["reason"]=="CANDIDATE_ONLY_NEEDS_INDEPENDENT_TZ_IDENTITY_AND_PIT"
    assert d["certified_provider_crosswalks"]==0
    assert d["certified_original_pit_rows"]==0
    assert d["production_p_matrix_authorized"] is False
    assert d["telegram_signal_authorized"] is False
    assert d["real_money"]=="BLOCKED"

def test_browser_after_kickoff_cannot_claim_prematch():
    b=browser()
    b["source_capture_at_utc"]["flashscore"]="2026-11-19T01:00:00+00:00"
    d=run(b=b)
    assert d["prematch_three_source_name_clock_hints"]==0
    assert d["rows"][0]["reason"]=="PRE_KICKOFF_SOURCE_CAPTURE_NOT_PROVEN"

def test_unknown_name_not_fuzzy_matched():
    b=browser()
    b["research_candidates"][0]["home_normalized"]="other coritiba"
    d=run(b=b)
    assert d["unique_provider_name_pair_matches"]==0
    assert d["rows"][0]["provider_fixture_id_name_match_only"] is None

def test_altered_bogota_clock_never_becomes_certified():
    b=browser()
    b["research_candidates"][0]["sofascore_visible_clock_unverified_timezone"]="18:00"
    d=run(b=b)
    assert d["rows"][0]["clock_agrees_if_sofascore_displays_bogota"] is False
    assert d["production_p_matrix_authorized"] is False

def test_duplicate_provider_name_pair_refused_as_identity():
    i=intake()
    copy=dict(i["fixtures"][0],source_fixture_id="555999")
    i["fixtures"].append(copy)
    d=run(i=i)
    assert d["unique_provider_name_pair_matches"]==0
    assert d["rows"][0]["reason"]=="PROVIDER_DUPLICATE_NAME_PAIR"

def test_untrusted_provider_admission_fails_closed():
    i=intake()
    i["fixtures"][0]["signal_generation_authorized"]=True
    with pytest.raises(ValueError,match="PROVIDER_ROW_UNTRUSTED"):
        run(i=i)

def test_day_mismatch_fails_closed():
    with pytest.raises(ValueError,match="RESEARCH_SOURCE_DATE_MISMATCH"):
        run(i=intake("2026-11-19"))


def test_main_rechecks_original_authorized_browser_sha_before_join(tmp_path, monkeypatch):
    """Never trust a crossmatch whose original raw browser bytes were altered."""
    from tools.matrix_football_free_browser_provider_research_join import main
    folder = tmp_path / "evidence" / "football_calendar_physical" / "2026-11-18"
    provider_folder = tmp_path / "evidence" / "football_world_inventory" / "2026-11-18"
    folder.mkdir(parents=True)
    provider_folder.mkdir(parents=True)
    original_sofa = b'{"source":"SOFASCORE","links":[]}'
    original_flash = b'{"source":"FLASHSCORE","links":[]}'
    (folder / "sofascore_visible_links.json").write_bytes(original_sofa)
    (folder / "flashscore_visible_links.json").write_bytes(original_flash)
    b = browser()
    b["telegram_signal_authorized"] = False
    b["research_candidate_count"] = 1
    b["source_sha256"] = {
        "sofascore": hashlib.sha256(original_sofa).hexdigest(),
        "flashscore": hashlib.sha256(original_flash).hexdigest(),
    }
    (folder / "MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json").write_text(json.dumps(b))
    (provider_folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
        json.dumps(intake())
    )
    monkeypatch.setattr(sys, "argv", ["research_join", "--day", "2026-11-18",
                                      "--root", str(tmp_path)])
    main()
    result_path = folder / "MATRIX_FOOTBALL_FREE_BROWSER_PROVIDER_RESEARCH_JOIN_LAST.json"
    result = json.loads(result_path.read_text())
    assert result["unique_provider_name_pair_matches"] == 1
    assert result["certified_provider_crosswalks"] == 0
    assert result["telegram_signal_authorized"] is False
    # Editing source bytes while retaining its old declared hash must fail.
    (folder / "sofascore_visible_links.json").write_bytes(original_sofa + b" ")
    with pytest.raises(ValueError, match="BROWSER_CAPTURE_HASH_CHANGED_AFTER_CROSSMATCH"):
        main()


def test_main_fails_closed_if_raw_browser_receipt_missing(tmp_path, monkeypatch):
    from tools.matrix_football_free_browser_provider_research_join import main
    folder = tmp_path / "evidence" / "football_calendar_physical" / "2026-11-18"
    provider_folder = tmp_path / "evidence" / "football_world_inventory" / "2026-11-18"
    folder.mkdir(parents=True)
    provider_folder.mkdir(parents=True)
    b = browser()
    b["research_candidate_count"] = 1
    b["source_sha256"] = {"sofascore": "a"*64, "flashscore": "b"*64}
    (folder / "MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json").write_text(json.dumps(b))
    (provider_folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
        json.dumps(intake())
    )
    monkeypatch.setattr(sys, "argv", ["research_join", "--day", "2026-11-18",
                                      "--root", str(tmp_path)])
    with pytest.raises(FileNotFoundError):
        main()
    assert not (folder / "MATRIX_FOOTBALL_FREE_BROWSER_PROVIDER_RESEARCH_JOIN_LAST.json").exists()
