"""Offline regression: source date labels and pre-registered triple fixture identity."""
from copy import deepcopy

import pytest
from tools.matrix_football_sofa_expanded_calendar_audit import reconcile

def fixtures():
    cross_ids=[("101","1001",12,30),("102","1002",14,45),
        ("103","1003",14,45),("104","1004",15,0),
        ("105","1005",15,0),("106","1006",15,15),
        ("107","1007",15,15),("108","1008",18,0)]
    capture={"schema":"MATRIX_OPERA_FOOTBALL_FULL_LINK_CAPTURE_V1",
             "source":"SOFASCORE","target_date_bogota":"2026-11-02",
             "source_order":["SOFASCORE","FLASHSCORE","APIS"],
             "observed_link_count":9,"explicit_target_date_label_count":8,
             "without_explicit_target_date_count":1,
             "telegram_authorized":False,"probability_authorized":False,
             "automatic_wagering":False,"real_money":"BLOCKED","observations":[]}
    sofa={"schema":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
          "target_date_bogota":"2026-11-02",
          "source_order":["SOFASCORE","FLASHSCORE","APIS"],
          "status":"PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL",
          "signal_generation_authorized":False,"rejected_count":0,
          "matched_count":8,"real_money":"BLOCKED","matched":[]}
    flash={"schema":"MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1",
           "target_date_bogota":"2026-11-02",
           "source_order":["SOFASCORE","FLASHSCORE","APIS"],
           "status":"PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS",
           "flashscore_verified":True,"signal_generation_authorized":False,
           "rejected_count":0,"matched_count":8,"real_money":"BLOCKED","matched":[]}
    independent={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
                 "target_date_bogota":"2026-11-02",
                 "source_order":["SOFASCORE","FLASHSCORE","APIS"],
                 "signal_generation_authorized":False,
                 "real_money":"BLOCKED","fixtures":[]}
    for i,(fid,sid,h,m) in enumerate(cross_ids):
        utc_hour=h+5
        if utc_hour>=24:
            raise ValueError("FIXTURE_CROSSES_UTC_DATE_UNHANDLED_IN_TEST")
        kickoff=f"2026-11-02T{utc_hour:02d}:{m:02d}:00+00:00"
        capture["observations"].append({
            "display_name":f"2/11/26 {h}:{m:02d} Home {i} Away {i}",
            "source_event_id":sid,
            "source_url":f"https://www.sofascore.com/es/football/match/home-away/{i}#id:{sid}",
            "explicit_target_date_label":True})
        sofa["matched"].append({"fixture_id":fid,"sofascore_event_id":sid,
                                 "kickoff_utc":kickoff})
        flash["matched"].append({"source_fixture_id":fid,"sofascore_event_id":sid,
                                  "flashscore_mid":f"MID_{i}",
                                  "kickoff_utc":kickoff})
        independent["fixtures"].append({"source_fixture_id":fid,"kickoff_utc":kickoff})
    capture["observations"].append({
        "display_name":"En Vivo Match Not Tomorrow",
        "source_event_id":"9999",
        "source_url":"https://www.sofascore.com/es/football/match/other-game/a#id:9999",
        "explicit_target_date_label":False})
    return capture,sofa,independent,flash

def test_eight_triple_source_fixtures_verified_against_full_calendar():
    c,s,i,f=fixtures()
    result=reconcile(c,s,i,f)
    assert result["status"]=="PASS_8_TRIPLE_SOURCE_MATCHES_ONLY_WIDER_SOFASCORE_BACKLOG"
    assert result["pre_registered_triple_source_matches"]==8
    assert result["observed_visible_links"]==9
    assert result["explicit_date_labeled_links"]==8
    assert result["without_explicit_date_label"]==1
    assert result["date_labeled_with_visible_kickoff_count"]==8
    assert result["date_labeled_without_visible_kickoff_count"]==0
    assert result["review_only_sofascore_links_without_independent_fixture"]==0
    assert result["telegram_signals_authorized"] is False
    assert result["real_money"]=="BLOCKED"

def test_event_removed_from_primary_page_blocks_confirmation():
    c,s,i,f=fixtures()
    c["observations"][0]["source_event_id"]="777"
    c["observations"][0]["source_url"]=c["observations"][0]["source_url"].replace("#id:1001","#id:777")
    result=reconcile(c,s,i,f)
    assert result["pre_registered_triple_source_matches"]==7
    assert result["pre_registered_rejections"][0]["reason"]=="SOFA_EVENT_NOT_PRESENT_IN_OBSERVED_CALENDAR"
    assert result["status"].startswith("BLOCKED_")

def test_wrong_kickoff_label_cannot_be_promoted():
    c,s,i,f=fixtures()
    c["observations"][0]["display_name"]=c["observations"][0]["display_name"].replace("12:30","13:30")
    result=reconcile(c,s,i,f)
    assert result["pre_registered_rejections"][0]["reason"]=="SOFA_VISIBLE_LOCAL_KICKOFF_MISMATCH"
    assert result["telegram_signals_authorized"] is False

def test_visible_overlapping_preview_is_not_dated():
    c,s,i,f=fixtures()
    c["observations"].append({"display_name":"Barcelona - Real Madrid",
                              "source_event_id":"7777",
                              "source_url":"https://www.sofascore.com/es/football/match/barca-real/a#id:7777",
                              "explicit_target_date_label":False})
    c["observed_link_count"]=10
    c["without_explicit_target_date_count"]=2
    result=reconcile(c,s,i,f)
    assert result["without_explicit_date_label"]==2
    assert result["pre_registered_triple_source_matches"]==8

def test_duplicate_event_id_rejected():
    c,s,i,f=fixtures()
    c["observations"].append(deepcopy(c["observations"][0]))
    c["observed_link_count"]+=1
    c["explicit_target_date_label_count"]+=1
    with pytest.raises(ValueError,match="DUPLICATE"):
        reconcile(c,s,i,f)

def test_corrupted_visible_date_flag_blocks():
    c,s,i,f=fixtures()
    c["observations"][0]["explicit_target_date_label"]=False
    with pytest.raises(ValueError,match="DATE_FLAG"):
        reconcile(c,s,i,f)

def test_false_calibration_signal_permission_blocks():
    c,s,i,f=fixtures()
    c["probability_authorized"]=True
    with pytest.raises(ValueError,match="FAIL_CLOSED"):
        reconcile(c,s,i,f)

def test_flash_provider_identity_necessary():
    c,s,i,f=fixtures()
    f["matched"][0]["sofascore_event_id"]="INVALID"
    result=reconcile(c,s,i,f)
    assert result["pre_registered_rejections"][0]["reason"]=="CROSS_PROVIDER_TIME_OR_ID_MISMATCH"

def test_wrong_source_date_rejected():
    c,s,i,f=fixtures()
    c["target_date_bogota"]="2026-11-03"
    with pytest.raises(ValueError,match="DATE_MISMATCH"):
        reconcile(c,s,i,f)

def test_explicit_date_without_kickoff_is_retained_but_quarantined():
    # Genuine SofaScore page labels may show 'Aplazado', 'Concedido' or 'FT'.
    # Preserve the event as dated without assigning an invented kickoff clock.
    c,s,i,f=fixtures()
    c["observations"].append({
        "display_name":"2/11/26 Aplazado Club A Club B",
        "source_event_id":"7777",
        "source_url":"https://www.sofascore.com/es/football/match/club-a-club-b/x#id:7777",
        "explicit_target_date_label":True,
    })
    c["observed_link_count"]+=1
    c["explicit_target_date_label_count"]+=1
    result=reconcile(c,s,i,f)
    assert result["explicit_date_labeled_links"]==9
    assert result["date_labeled_with_visible_kickoff_count"]==8
    assert result["date_labeled_without_visible_kickoff_count"]==1
    assert result["date_labeled_without_visible_kickoff_ids"]==["7777"]
    assert result["pre_registered_triple_source_matches"]==8
    assert result["review_only_sofascore_links_without_independent_fixture"]==1
    assert result["telegram_signals_authorized"] is False


def test_pre_registered_fixture_without_visible_kickoff_fails_closed():
    c,s,i,f=fixtures()
    c["observations"][0]["display_name"]="2/11/26 Concedido Home 0 Away 0"
    result=reconcile(c,s,i,f)
    assert result["pre_registered_triple_source_matches"]==7
    assert result["status"].startswith("BLOCKED_")
    assert result["pre_registered_rejections"][0]["reason"]=="SOURCE_EVENT_EXACT_KICKOFF_TIME_NOT_VISIBLE"
    assert result["telegram_signals_authorized"] is False
