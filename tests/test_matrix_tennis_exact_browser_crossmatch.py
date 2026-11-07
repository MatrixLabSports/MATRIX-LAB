import json
from pathlib import Path
from tools.matrix_tennis_exact_browser_crossmatch import reconcile,identity

def sample(root,second_source=True):
    base=root/"evidence/tennis_calendar_physical/2026-11-04"
    base.mkdir(parents=True)
    sources=[
        ("SOFASCORE","sofascore_opera_full_link_observations.json",
         "https://www.sofascore.com/es/tennis/match/tomas-martin-etcheverry-andrey-rublev/fKRsWOrb#id:17449521"),
        ("FLASHSCORE","flashscore_opera_full_link_observations.json",
         "https://www.flashscore.co/partido/tenis/etcheverry-tomas-martin-AXL5qpKa/rublev-andrey-AeAn4gP0/?mid=d6ydpGF7")]
    for source,name,url in (sources if second_source else sources[:1]):
        doc={"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
            "source":source,"target_date_bogota":"2026-11-04",
            "real_money":"BLOCKED","canonical_fixture_export_authorized":False,
            "probability_generation_authorized":False,
            "matches":[{"url":url,"display_name":"Tomas Martin Etcheverry Andrey Rublev"}]}
        (base/name).write_text(json.dumps(doc))

def test_same_players_exact_name_tokens_is_hint_not_verified_event(tmp_path):
    sample(tmp_path)
    r=reconcile(tmp_path,"2026-11-04")
    assert r["matched_exact_name_hints"]==1
    row=r["matches"][0]
    assert row["sofascore_id"]=="17449521"
    assert row["flashscore_mid"]=="d6ydpGF7"
    assert row["same_event_verified"] is False
    assert row["surface_verified"] is False
    assert r["hard_holdout_admitted"]==0
    assert r["clay_holdout_admitted"]==0

def test_missing_second_source_blocks(tmp_path):
    sample(tmp_path,second_source=False)
    r=reconcile(tmp_path,"2026-11-04")
    assert r["status"]=="REQUIRED_SOURCE_NOT_CAPTURED"
    assert r["matched_exact_name_hints"]==0

def test_duplicate_competitions_do_not_create_confident_identity(tmp_path):
    sample(tmp_path)
    f=tmp_path/"evidence/tennis_calendar_physical/2026-11-04/sofascore_opera_full_link_observations.json"
    d=json.loads(f.read_text())
    d["matches"].append({"url":"https://www.sofascore.com/es/tennis/match/tomas-martin-etcheverry-andrey-rublev/zzzzzz#id:9999999"})
    f.write_text(json.dumps(d))
    r=reconcile(tmp_path,"2026-11-04")
    assert r["matched_exact_name_hints"]==0

def test_untrusted_link_domain_fails_identity():
    assert identity("SOFASCORE",{"url":"https://evil.example/es/tennis/match/tomas-martin-etcheverry-andrey-rublev/z#id:1"}) is None
