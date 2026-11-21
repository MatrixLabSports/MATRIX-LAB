from copy import deepcopy
import pytest
from tools.matrix_tennis_opera_dual_source_link_audit import review

SOFA_URL="https://www.sofascore.com/es/tennis/match/adrian-andreev-massimo-giunta/JhhbszBIb#id:17466755"
FLASH_URL="https://www.flashscore.co/partido/tenis/andreev-adrian-8zKQSxfi/giunta-massimo-hQkb3GZ8/?mid=OO5oW5Yi"

def captures():
    base={"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
          "target_date_bogota":"2026-11-02",
          "source_order":["SOFASCORE","FLASHSCORE","APIS"],
          "real_money":"BLOCKED","telegram_signals_authorized":False,
          "automatic_wagering":False,"canonical_fixture_export_authorized":False}
    sofa={**base,"source":"SOFASCORE","observed_link_count":1,
          "matches":[{"display_name":"2/11/26 4:00 Italy M. Giunta Bulgaria A. Andreev",
                      "source_event_id":"17466755","url":SOFA_URL}]}
    flash={**base,"source":"FLASHSCORE","observed_link_count":1,
           "matches":[{"display_name":"Giunta M. - Andreev A.",
                       "source_event_id":"giunta-massimo-hQkb3GZ8","url":FLASH_URL}]}
    return sofa,flash

def test_two_real_provider_full_player_slug_sets_form_review_candidate():
    a,b=captures()
    v=review(a,b)
    assert v["candidate_pair_count"]==1
    assert v["source_counts"]["sofascore_explicit_target_date_links"]==1
    assert v["candidate_pairs"][0]["same_fixture_certified"] is False
    assert v["utc_kickoff_certified"] is False
    assert v["surface_certified"] is False
    assert v["signal_generation_authorized"] is False
    assert v["calibration_parameters_modified"] is False
    assert v["real_money"]=="BLOCKED"

def test_link_not_explicitly_dated_never_produces_candidate():
    a,b=captures()
    a["matches"][0]["display_name"]="En Vivo M. Giunta A. Andreev"
    r=review(a,b)
    assert r["candidate_pair_count"]==0
    assert r["source_counts"]["sofascore_without_target_date"]==1

def test_tomorrow_another_date_does_not_match():
    a,b=captures()
    a["matches"][0]["display_name"]="3/11/26 4:00 Giunta - Andreev"
    assert review(a,b)["candidate_pair_count"]==0

def test_unstructured_doubles_event_does_not_generate_pair():
    a,b=captures()
    b["matches"][0]["url"]="https://www.flashscore.co/partido/tenis/0KZYCbTp/"
    r=review(a,b)
    assert r["candidate_pair_count"]==0
    assert r["source_counts"]["flashscore_unstructured_links"]==1

def test_different_opponent_cannot_be_inferred():
    a,b=captures()
    b["matches"][0]["url"]=FLASH_URL.replace("giunta-massimo-hQkb3GZ8","norrie-cameron-pvzhJGY8")
    assert review(a,b)["candidate_pair_count"]==0

def test_duplicate_preview_url_for_same_player_pair_not_two_events():
    a,b=captures()
    preview={"display_name":"Giunta - Andreev",
             "url":FLASH_URL.split("?")[0],
             "source_event_id":"giunta-massimo-hQkb3GZ8"}
    b["matches"].append(preview)
    b["observed_link_count"]=2
    r=review(a,b)
    assert r["candidate_pair_count"]==1
    assert r["source_counts"]["flashscore_named_player_pair_unique_links"]==1

def test_bad_sofa_id_fails_closed():
    a,b=captures()
    a["matches"][0]["source_event_id"]="FAKE"
    with pytest.raises(ValueError,match="SOFA_URL_EVENT_ID"):
        review(a,b)

def test_wrong_day_and_untrusted_source_fail_closed():
    a,b=captures()
    b["target_date_bogota"]="2026-11-03"
    with pytest.raises(ValueError,match="DATE"):
        review(a,b)
    a,b=captures()
    b["source"]="RAPIDAPI"
    with pytest.raises(ValueError,match="SOURCE_ORDER"):
        review(a,b)

def test_duplicate_sofa_link_does_not_count_twice():
    a,b=captures()
    a["matches"].append(deepcopy(a["matches"][0]))
    a["observed_link_count"]=2
    with pytest.raises(ValueError,match="DUPLICATED_SOURCE_URLS"):
        review(a,b)

def test_observed_links_can_never_enable_money_or_telegram():
    a,b=captures()
    a["telegram_signals_authorized"]=True
    with pytest.raises(ValueError,match="GOVERNANCE"):
        review(a,b)
    a,b=captures()
    b["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="GOVERNANCE"):
        review(a,b)
