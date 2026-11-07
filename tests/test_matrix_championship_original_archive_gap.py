import json
from pathlib import Path
from tools.matrix_championship_original_archive_gap import inspect


def _feed(root):
    d = root/"evidence/football_world_inventory/2026-11-03"
    d.mkdir(parents=True)
    (d/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json").write_text(json.dumps({
        "schema":"MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1",
        "real_money":"BLOCKED", "signal_generation_authorized":False,
        "matched":[{"source_fixture_id":"561921","three_source_calendar_identity_verified":True},
                   {"source_fixture_id":"561917","three_source_calendar_identity_verified":True},
                   {"source_fixture_id":"561920","three_source_calendar_identity_verified":False}],
    }), encoding="utf-8")
    (d/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json").write_text(json.dumps({
        "schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
        "market_signal_authorized":False,
        "scored":[
          {"source_fixture_id":"561921","competition_id":2016,
           "home":"Derby County","away":"Norwich City",
           "p_over25_research":0.6172471641},
          {"source_fixture_id":"561917","competition_id":2016,
           "home":"Birmingham City","away":"Millwall",
           "p_over25_research":0.6024946159},
          {"source_fixture_id":"561920","competition_id":2016,
           "home":"QPR","away":"Burnley","p_over25_research":0.99},
          {"source_fixture_id":"555073","competition_id":2013,
           "home":"Chapecoense","away":"Mirassol","p_over25_research":0.91},
        ]
    }), encoding="utf-8")


def test_missing_archived_championship_detected_and_no_guessed_production(tmp_path):
    _feed(tmp_path)
    report = inspect(tmp_path)
    assert report["status"]=="FAIL_CLOSED_NO_ORIGINAL_CHAMPIONSHIP_2026_RAW_ARCHIVE_IN_CHECKOUT"
    assert report["original_championship_group_archives_found"]==0
    rows=report["cross_source_matches_with_research_p_at_least_0_60"]
    assert {x["source_fixture_id"] for x in rows}=={"561921","561917"}
    assert all(x["governed_original_p_matrix"] is None for x in rows)
    assert report["new_model_probabilities_generated"]==0
    assert report["telegram_signals_authorized"] is False


def test_discovered_archived_group_is_recorded_but_not_automatically_promoted(tmp_path):
    _feed(tmp_path)
    root=tmp_path/"evidence/api_football/prospective_daily/2026-10-25/abc/history/raw"
    root.mkdir(parents=True)
    (root/"league_40_season_2026.bin").write_bytes(b"original-immmutable-raw")
    report=inspect(tmp_path)
    assert report["status"]=="ORIGINAL_CHAMPIONSHIP_ARCHIVE_FOUND_PARITY_STILL_REQUIRED"
    assert report["original_championship_group_archives_found"]==1
    assert report["original_championship_archive_paths"][0]["bytes"]==len(b"original-immmutable-raw")
    assert report["telegram_signals_authorized"] is False


def test_untrusted_signal_promotion_inside_crosscheck_rejected(tmp_path):
    import pytest
    _feed(tmp_path)
    p=tmp_path/"evidence/football_world_inventory/2026-11-03/MATRIX_FLASH_FOOTBALL_CROSSCHECK.json"
    j=json.loads(p.read_text())
    j["signal_generation_authorized"]=True
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError,match="CROSSCHECK_NOT_SIGNAL_SAFE"):
        inspect(tmp_path)
