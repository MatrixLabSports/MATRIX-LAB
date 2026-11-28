"""Research-only third-party calendar targets must NEVER become MATRIX picks."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.matrix_selfhosted_browser_quote_collector import (
    independent_research_quote_targets, atomic_verified_research_quote_targets, quote_eligibility,
)

NOW=datetime(2026,11,3,19,0,tzinfo=timezone.utc)
DAY="2026-11-03"


def _fixtures(root:Path,*,same_kickoff=True):
    folder=root/"evidence"/"football_world_inventory"/DAY
    folder.mkdir(parents=True)
    kickoff="2026-11-03T19:45:00+00:00"
    source={
      "schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
      "provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
      "source":"FOOTBALL_DATA_ORG","target_date_bogota":DAY,
      "generated_at_utc":"2026-11-03T18:30:00+00:00",
      "real_money":"BLOCKED","signal_generation_authorized":False,
      "fixture_count":1,"fixtures":[{
        "source":"FOOTBALL_DATA_ORG","source_fixture_id":"561918",
        "home":"Portsmouth FC","away":"Swansea City AFC",
        "kickoff_utc":kickoff,"api_football_fixture_id":None,
        "signal_generation_authorized":False
      }]
    }
    sofa={
      "real_money":"BLOCKED","signal_generation_authorized":False,
      "target_date_bogota":DAY,"matched_count":1,
      "matched":[{"fixture_id":"561918","sofascore_event_id":"16391597",
        "identity_time_and_teams_verified":True,"kickoff_utc":kickoff}]
    }
    flash={
      "real_money":"BLOCKED","signal_generation_authorized":False,
      "target_date_bogota":DAY,"matched_count":1,
      "flashscore_verified":True,"sofascore_verified":True,
      "matched":[{"source_fixture_id":"561918","sofascore_event_id":"16391597",
        "flashscore_mid":"4tCThItm",
        "three_source_calendar_identity_verified":True,
        "kickoff_utc":kickoff if same_kickoff else "2026-11-03T20:45:00+00:00"}]
    }
    for name,doc in (
      ("MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",source),
      ("MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",sofa),
      ("MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",flash)
    ):
      (folder/name).write_text(json.dumps(doc),encoding="utf-8")
    return folder,source,sofa,flash


def test_triple_source_research_target_has_no_model_probability(tmp_path):
    _fixtures(tmp_path)
    rows=independent_research_quote_targets(NOW,tmp_path)
    assert len(rows)==1
    row=rows[0]
    assert row["fixture_id"]=="FOOTBALL_DATA_ORG:561918"
    assert row["match"]=="Portsmouth FC vs Swansea City AFC"
    assert row["p_matrix"] is None
    assert row["research_only"] is True
    assert row["telegram_signal_authorized"] is False
    assert row["production_probability_authorized"] is False
    allowed,reason=quote_eligibility({"price":2.11},row,"CERTIFIED_EXACT_OVER25",NOW)
    assert allowed is False
    assert reason=="NO_SIGNAL_ECONOMIC_GATE"


def test_outside_prematch_window_does_not_discover_stale_quotes(tmp_path):
    _fixtures(tmp_path)
    assert independent_research_quote_targets(NOW-timedelta(hours=3),tmp_path)==[]
    assert independent_research_quote_targets(NOW+timedelta(hours=2),tmp_path)==[]


def test_mismatched_triple_source_kickoff_blocks_research(tmp_path):
    _fixtures(tmp_path,same_kickoff=False)
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_missing_or_duplicate_event_identity_blocks_research(tmp_path):
    folder,source,sofa,flash=_fixtures(tmp_path)
    flash["matched"][0]["sofascore_event_id"]="WRONG"
    (folder/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json").write_text(json.dumps(flash))
    assert independent_research_quote_targets(NOW,tmp_path)==[]
    flash["matched"][0]["sofascore_event_id"]="16391597"
    flash["matched"].append(dict(flash["matched"][0]))
    flash["matched_count"]=2
    (folder/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json").write_text(json.dumps(flash))
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_expired_source_capture_blocks_research(tmp_path):
    folder,source,_,_=_fixtures(tmp_path)
    source["generated_at_utc"]="2026-11-01T01:00:00+00:00"
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(json.dumps(source))
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_provider_or_governance_mismatch_blocks_research(tmp_path):
    folder,source,_,_=_fixtures(tmp_path)
    source["provider_status"]="MISSING_FOOTBALL_DATA_ORG_TOKEN"
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(json.dumps(source))
    assert independent_research_quote_targets(NOW,tmp_path)==[]
    source["provider_status"]="AUTHENTICATED_FIXTURE_CAPTURE"
    source["signal_generation_authorized"]=True
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(json.dumps(source))
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_missing_source_is_not_synthetic_data(tmp_path):
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_real_seven_three_source_archive_yields_six_research_only_targets():
    """Offline replay of immutable 03-Nov evidence; not a live quote or bet."""
    root=Path(__file__).resolve().parents[1]
    clock=datetime(2026,11,3,19,0,tzinfo=timezone.utc)
    rows=independent_research_quote_targets(clock,root)
    ids={r["fixture_id"] for r in rows}
    assert ids=={
      "FOOTBALL_DATA_ORG:561917",
      "FOOTBALL_DATA_ORG:561918",
      "FOOTBALL_DATA_ORG:561921",
      "FOOTBALL_DATA_ORG:561922",
      "FOOTBALL_DATA_ORG:561924",
      "FOOTBALL_DATA_ORG:561928",
    }
    assert all(r["research_only"] is True and r["p_matrix"] is None
               and r["telegram_signal_authorized"] is False for r in rows)


def test_real_six_immutable_pit_fixtures_feed_readonly_browser_lookup():
    root=Path(__file__).resolve().parents[1]
    when=datetime(2026,11,3,19,0,tzinfo=timezone.utc)
    folder=root/"evidence"/"football_world_inventory"/"2026-11-03"
    rows=atomic_verified_research_quote_targets(when,folder,"2026-11-03")
    assert rows is not None
    assert {r["fixture_id"] for r in rows}=={
      "FOOTBALL_DATA_ORG:561917","FOOTBALL_DATA_ORG:561918",
      "FOOTBALL_DATA_ORG:561921","FOOTBALL_DATA_ORG:561922",
      "FOOTBALL_DATA_ORG:561924","FOOTBALL_DATA_ORG:561928"}
    assert len({r["atomic_attestation_sha256"] for r in rows})==1
    assert all(r["atomic_pit_bundle"].startswith("evidence/football_world_inventory/")
               for r in rows)
    for row in rows:
        assert row["p_matrix"] is None
        assert row["research_only"] is True
        assert row["production_probability_authorized"] is False
        assert row["telegram_signal_authorized"] is False
        assert row["original_enriched_model_parity_verified"] is False
        allowed,reason=quote_eligibility({"price":2.25},row,
                                         "CERTIFIED_EXACT_OVER25",when)
        assert not allowed and reason=="NO_SIGNAL_ECONOMIC_GATE"


def test_tampered_atomic_bundle_blocks_even_if_daily_triple_sources_look_valid(tmp_path):
    folder,source,sofa,flash=_fixtures(tmp_path)
    f=folder/"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_999.json"
    f.write_text(json.dumps({"schema":"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_CYCLE_V1",
                             "documents":{"intake":{"source":"FAKE"}}}),
                 encoding="utf-8")
    assert atomic_verified_research_quote_targets(NOW,folder,DAY)==[]
    assert independent_research_quote_targets(NOW,tmp_path)==[]


def test_existing_real_atomic_does_not_use_postkickoff_price_or_probability():
    root=Path(__file__).resolve().parents[1]
    time=datetime(2026,11,3,21,0,tzinfo=timezone.utc)
    rows=independent_research_quote_targets(time,root)
    assert not any(x["fixture_id"]=="FOOTBALL_DATA_ORG:561918" for x in rows)


def test_mutable_daily_file_changes_do_not_mutate_immutable_quote_targets(tmp_path):
    import shutil
    folder,source,sofa,flash=_fixtures(tmp_path)
    root=Path(__file__).resolve().parents[1]
    proof=root/"evidence"/"football_world_inventory"/DAY/"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_41652244354.json"
    assert proof.is_file()
    shutil.copy2(proof,folder/proof.name)
    original=independent_research_quote_targets(NOW,tmp_path)
    assert len(original)==6
    source["fixtures"][0]["home"]="Invented team"
    (folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json").write_text(
        json.dumps(source),encoding="utf-8")
    changed=independent_research_quote_targets(NOW,tmp_path)
    assert changed==original
