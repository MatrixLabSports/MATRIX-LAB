"""Synthetic DOM fixtures are tests, never actual tennis observations."""
from datetime import datetime, timezone
from pathlib import Path
import pytest
from tools.matrix_tennis_browser_verified_detail_capture import eligible_priorities, parse_visible
from tools.matrix_tennis_browser_first_free_intake import get

DAY="2026-11-06"
P=Path("evidence/tennis_calendar_reconciliation")/DAY/"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json"

def inputs():
    j,_=get(Path.cwd(),P)
    row=next(x for x in eligible_priorities(Path.cwd(),j) if x["sofascore_id"]=="17427360")
    src=row["sofascore_url"]
    links=[
        {"url":"https://www.sofascore.com/es/tennis/player/basavareddy-nishesh/407164","name":"Nishesh Basavareddy"},
        {"url":"https://www.sofascore.com/es/tennis/player/basavareddy-nishesh/407164","name":"Nishesh Basavareddy USA ATP 128º"},
        {"url":"https://www.sofascore.com/es/tennis/player/kym-jerome/309071","name":"Jerome Kym"},
        {"url":"https://www.sofascore.com/es/tennis/player/kym-jerome/309071","name":"Jerome Kym Switzerland ATP 164º"},
        {"url":"https://www.sofascore.com/es/tennis/tournament/challenger/bratislava-slovakia/14402#id:96701","name":"Competición Tenis, Challenger 125, Bratislava 2, Slovakia, Cuartos de final"},
        {"url":"https://calendar.google.com/calendar/render?action=TEMPLATE&dates=20261106T132000Z%2F20261106T152000Z&details="+__import__("urllib.parse",fromlist=["quote"]).quote(src,safe=""),
         "name":"Fecha y hora 6/11/2026 8:20 Añade al calendario"},
    ]
    return row,{"page_url":src,"visible_text":"Cuartos de final Dura indoor","links":links}

def test_prematch_detail_shape_keeps_all_model_gates_closed():
    row,ui=inputs()
    x=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert x["surface"]=="Hard"
    assert x["kickoff_utc"]=="2026-11-06T13:20:00Z"
    assert x["local_visible_time"]=="8:20"
    assert {v["name"] for v in x["players"]}=={"Nishesh Basavareddy","Jerome Kym"}
    assert x["provider_player_id_equivalence_certified"] is False

def test_no_false_detail_on_missing_surface_or_calendar_or_late_capture():
    row,ui=inputs()
    ui["visible_text"]="No court label"
    with pytest.raises(ValueError,match="SURFACE"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    row,ui=inputs()
    ui["links"]=[a for a in ui["links"] if "calendar.google.com" not in a["url"]]
    with pytest.raises(ValueError,match="GOOGLE_CALENDAR"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    row,ui=inputs()
    with pytest.raises(ValueError,match="PROSPECTIVE_WINDOW_CLOSED"):
        parse_visible(row,ui,DAY,datetime(2026,11,6,13,20,tzinfo=timezone.utc))

def test_authority_pair_priority_from_original_immutable_sources():
    cross,_=get(Path.cwd(),P)
    picks=eligible_priorities(Path.cwd(),cross)
    ids={str(x["sofascore_id"]) for x in picks}
    assert {"17427360","17427339","17427540"}<=ids
