from copy import deepcopy
import pytest
from tools.matrix_tennis_opera_03nov_link_audit import review

SOFA_URL="https://www.sofascore.com/es/tennis/match/adrian-andreev-massimo-giunta/JhhbszBIb#id:17466755"
FLASH_URL="https://www.flashscore.co/partido/tenis/andreev-adrian-8zKQSxfi/giunta-massimo-hQkb3GZ8/?mid=OO5oW5Yi"

def captures():
    base={"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
          "target_date_bogota":"2026-11-03",
          "source_order":["SOFASCORE","FLASHSCORE","APIS"],
          "real_money":"BLOCKED","telegram_signals_authorized":False,
          "automatic_wagering":False,"canonical_fixture_export_authorized":False,
          "probability_generation_authorized":False,"model_calibration_unchanged":True}
    sofa={**base,"source":"SOFASCORE","observed_link_count":1,
          "source_page_url":"https://www.sofascore.com/es/tennis/2026-11-03",
          "matches":[{"display_name":"3/11/26 4:00 Italy M. Giunta Bulgaria A. Andreev",
                      "explicit_target_date_label":True,"visible_local_clock":True,
                      "source_event_id":"17466755","url":SOFA_URL}]}
    flash={**base,"source":"FLASHSCORE","observed_link_count":1,
           "source_page_url":"https://www.flashscore.co/tenis/manana/",
           "date_selector_accessibility_label":"martes, 3 de noviembre de 2026",
           "individual_match_date_verified":False,
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
    a["matches"][0]["explicit_target_date_label"]=False
    a["matches"][0]["visible_local_clock"]=False
    r=review(a,b)
    assert r["candidate_pair_count"]==0
    assert r["source_counts"]["sofascore_without_target_date"]==1

def test_tomorrow_another_date_does_not_match():
    a,b=captures()
    a["matches"][0]["display_name"]="4/11/26 4:00 Giunta - Andreev"
    a["matches"][0]["explicit_target_date_label"]=False
    a["matches"][0]["visible_local_clock"]=False
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
    b["target_date_bogota"]="2026-11-04"
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

def test_flashscore_calendar_selector_must_match_target_day():
    a,b=captures()
    b["date_selector_accessibility_label"]="lunes, 2 de noviembre de 2026"
    with pytest.raises(ValueError,match="FLASH_DATE_CONTEXT_INVALID"):
        review(a,b)

def test_flagged_date_or_clock_not_visible_blocks_capture():
    a,b=captures()
    a["matches"][0]["display_name"]="3/11/26 Aplazado Italy M. Giunta Bulgaria A. Andreev"
    with pytest.raises(ValueError,match="SOFA_VISIBLE_DATE_OR_CLOCK_FLAG_INVALID"):
        review(a,b)

def test_genuine_dated_entry_without_time_kept_but_uncertified():
    a,b=captures()
    a["matches"][0]["display_name"]="3/11/26 Aplazado Italy M. Giunta Bulgaria A. Andreev"
    a["matches"][0]["visible_local_clock"]=False
    r=review(a,b)
    assert r["source_counts"]["sofascore_date_without_visible_clock"]==1
    assert r["utc_kickoff_certified"] is False
    assert r["signal_generation_authorized"] is False

def test_no_model_calibration_mutation_or_source_probability_promotion():
    a,b=captures()
    a["probability_generation_authorized"]=True
    with pytest.raises(ValueError,match="CAPTURE_GOVERNANCE_INVALID"):
        review(a,b)
    a,b=captures()
    b["model_calibration_unchanged"]=False
    with pytest.raises(ValueError,match="CAPTURE_GOVERNANCE_INVALID"):
        review(a,b)
