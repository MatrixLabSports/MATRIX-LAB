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
    with pytest.raises(ValueError,match="MATCH_SOURCE_EXPLICIT_UTC_CLOCK_MISSING"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    row,ui=inputs()
    with pytest.raises(ValueError,match="PROSPECTIVE_WINDOW_CLOSED"):
        parse_visible(row,ui,DAY,datetime(2026,11,6,13,20,tzinfo=timezone.utc))

def test_authority_pair_priority_from_original_immutable_sources():
    cross,_=get(Path.cwd(),P)
    picks=eligible_priorities(Path.cwd(),cross)
    ids={str(x["sofascore_id"]) for x in picks}
    assert {"17427360","17427339","17427540"}<=ids


def test_accessible_aria_label_is_source_of_competition_and_local_calendar_clock():
    row,ui=inputs()
    for link in ui["links"]:
        if "tournament/challenger/" in link["url"]:
            link["label"]=link["name"]
            link["name"]="Bratislava"
        if "calendar.google.com" in link["url"]:
            link["label"]=link["name"]
            link["name"]="Añadir al calendario"
    result=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert result["surface"]=="Hard"
    assert result["local_visible_time"]=="8:20"
    assert result["round"]=="Cuartos de final"
    assert result["provider_player_id_equivalence_certified"] is False


def test_new_visible_countries_are_not_rejected_by_old_five_country_subset():
    from tools.matrix_tennis_browser_verified_detail_capture import visible_country_candidates
    assert visible_country_candidates([{"name":"S. Example France","label":"","flag_alts":[]}])==["France"]
    assert visible_country_candidates([{"name":"S. Example","label":"Nacionalidad España","flag_alts":[]}])==["Spain"]
    assert visible_country_candidates([{"name":"S. Example","label":"","flag_alts":["Italy"]}])==["Italy"]


def test_country_not_inferred_from_global_page_or_last_name():
    from tools.matrix_tennis_browser_verified_detail_capture import visible_country_candidates
    assert visible_country_candidates([{"name":"Francesco Test","label":"","flag_alts":[]}])==[]
    assert visible_country_candidates([{"name":"S. Example","label":"Novak Test","flag_alts":[]}])==[]


def test_ambiguous_two_countries_on_same_profile_fail_closed():
    row,ui=inputs()
    for item in ui["links"]:
        if "/player/kym-jerome/" in item["url"] and "Switzerland" in item["name"]:
            item["label"]="France"
    with pytest.raises(ValueError,match="VISIBLE_PLAYER_COUNTRY_MISSING_OR_AMBIGUOUS"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_windows_workflow_defers_pit_until_current_detail_capture():
    # A stale detail snapshot must never block new capture merely because
    # the current calendar crossmatch got refreshed first.
    workflow=(Path(__file__).resolve().parents[1]/
              ".github/workflows/matrix-selfhosted-tennis-browser-free-30m.yml").read_text()
    marker='      - name: Capture source-visible individual Challenger details and run governed PIT gate'
    assert marker in workflow
    pre, post = workflow.split(marker,1)
    assert 'TENNIS_PIT_GATE_DEFERRED_UNTIL_CURRENT_DETAIL_CAPTURE_NO_ADMISSION' in pre
    assert 'python -m tools.matrix_tennis_browser_challenger_pit_gate --date $day' not in pre
    assert 'python -m tools.matrix_tennis_browser_verified_detail_capture --date $day' in post
    assert 'python -m tools.matrix_tennis_browser_challenger_pit_gate --date $day' in post
    assert 'TENNIS_NO_AUTHENTIC_CHALLENGER_DETAILS_ANY_DATE' in post


def test_failed_match_keeps_only_bounded_public_visible_evidence():
    from tools.matrix_tennis_browser_verified_detail_capture import public_visible_failure_clues
    row,ui=inputs()
    ui["links"].append({"url":"https://evil.example/token?secret=1","name":"unsafe"})
    ui["links"].append({"url":"https://www.sofascore.com/es/tennis/player/example/123?session=private",
                        "name":"Example","label":"France","flag_alts":["France"]})
    result=public_visible_failure_clues(ui)
    assert len(result["visible_page_sha256"])==64
    assert result["not_individual_identity_certification"] is True
    assert all("evil.example" not in x["url"] for x in result["visible_source_links"])
    assert all("session=" not in x["url"] for x in result["visible_source_links"])
    assert any(x["label"]=="France" for x in result["visible_source_links"])
    assert public_visible_failure_clues(None) is None


def test_current_public_challenger_tournament_label_without_fixed_prefix():
    row,ui=inputs()
    for link in ui["links"]:
        if "/tournament/challenger/" in link["url"]:
            link["name"]="Bratislava, Slovakia, Cuartos de final"
            link["label"]=""
    event=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert event["competition_label"]=="Bratislava, Slovakia, Cuartos de final"
    assert event["tournament_name"]=="Bratislava, Slovakia"
    assert event["round"]=="Cuartos de final"
    assert event["challenger_category_evidenced_by_tournament_url"] is True
    assert event["provider_player_id_equivalence_certified"] is False


def test_challenger_category_cannot_come_from_text_without_real_url():
    row,ui=inputs()
    for link in ui["links"]:
        if "/tournament/challenger/" in link["url"]:
            link["url"]="https://www.sofascore.com/es/tennis/tournament/atp-fake/111"
            link["name"]="Bratislava, Slovakia, Cuartos de final"
    with pytest.raises(ValueError,match="EXACT_CHALLENGER_COMPETITION_LINK_REQUIRED"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_challenger_round_must_be_explicitly_visible_not_guessed():
    row,ui=inputs()
    for link in ui["links"]:
        if "/tournament/challenger/" in link["url"]:
            link["name"]="Bratislava, Slovakia"
            link["label"]=""
    with pytest.raises(ValueError,match="EXACT_CHALLENGER_COMPETITION_LINK_REQUIRED"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_explicit_china_flag_is_read_without_identity_inference():
    from tools.matrix_tennis_browser_verified_detail_capture import visible_country_candidates
    assert visible_country_candidates([
        {"name":"Y. Zhou","label":"","flag_alts":["Yi Zhou","China"]}
    ])==["China"]


def test_same_challenger_multiple_visible_labels_are_one_verified_tournament():
    row,ui=inputs()
    for link in ui["links"]:
        if "/tournament/challenger/" in link["url"]:
            link["name"]="Bratislava, Slovakia, Cuartos de final"
            link["label"]=""
    ui["links"].append({"url":next(x["url"] for x in ui["links"]
                             if "/tournament/challenger/" in x["url"]),
                        "name":"Competición\nTenis, Challenger 125, Bratislava, Slovakia, Cuartos de final",
                        "label":"","flag_alts":[]})
    event=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert event["tournament_name"]=="Bratislava, Slovakia"
    assert event["round"]=="Cuartos de final"
    assert event["competition_label"]=="Bratislava, Slovakia, Cuartos de final"


def test_two_different_visible_rounds_for_same_tournament_fail_closed():
    row,ui=inputs()
    ui["links"].append({"url":next(x["url"] for x in ui["links"]
                             if "/tournament/challenger/" in x["url"]),
                        "name":"Bratislava, Slovakia, Semifinal",
                        "label":"","flag_alts":[]})
    with pytest.raises(ValueError,match="EXACT_CHALLENGER_COMPETITION_LINK_REQUIRED"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_public_failure_clues_show_bounded_calendar_shape_and_court_presence():
    from tools.matrix_tennis_browser_verified_detail_capture import public_visible_failure_clues
    row,ui=inputs()
    report=public_visible_failure_clues(ui)
    assert report["public_calendar_link_count"]==1
    assert report["public_calendar_link_diagnostics"][0]["action_template"] is True
    assert report["public_calendar_link_diagnostics"][0]["exact_utc_date_range_shape"] is True
    assert "Dura indoor" in report["visible_court_term_presence_only"]
    assert report["not_individual_identity_certification"] is True
    assert all("calendar.google.com" not in x["url"] for x in report["visible_source_links"])


def test_public_failure_clues_never_claim_missing_clock_or_court_is_verified():
    from tools.matrix_tennis_browser_verified_detail_capture import public_visible_failure_clues
    row,ui=inputs()
    ui["links"]=[v for v in ui["links"] if "calendar.google.com" not in v["url"]]
    ui["visible_text"]="Players and standings only"
    report=public_visible_failure_clues(ui)
    assert report["public_calendar_link_count"]==0
    assert report["visible_court_term_presence_only"]==[]
    assert report["not_individual_identity_certification"] is True


def test_visible_dura_outdoor_is_hard_without_inference():
    row,ui=inputs()
    ui["visible_text"]="Cuartos de final Dura outdoor"
    event=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert event["surface"]=="Hard"
    assert event["court_label"]=="Dura outdoor"
    assert event["provider_player_id_equivalence_certified"] is False


def test_outdoor_alone_cannot_certify_hard_surface():
    row,ui=inputs()
    ui["visible_text"]="Cuartos de final Superficie outdoor"
    with pytest.raises(ValueError,match="EXACT_COURT_SURFACE_MISSING_OR_AMBIGUOUS"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_hard_and_clay_visible_simultaneously_block_surface():
    row,ui=inputs()
    ui["visible_text"]="Cuartos de final Dura outdoor Tierra batida"
    with pytest.raises(ValueError,match="EXACT_COURT_SURFACE_MISSING_OR_AMBIGUOUS"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_visible_sport_page_explicit_utc_works_without_calendar_button():
    # This clock shape was directly observed in the authorized public
    # SofaScore accessibility tree on 11-Nov-2026. Synthetic fixture only.
    row,ui=inputs()
    ui["links"]=[x for x in ui["links"] if "calendar.google.com" not in x["url"]]
    ui["visible_text"]="Cuartos de final Dura indoor. El partido comienza el 6 nov 2026 a las 13:20 UTC en Bratislava."
    event=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert event["kickoff_utc"]=="2026-11-06T13:20:00Z"
    assert event["calendar_date_token"]=="20261106T132000Z"
    assert event["kickoff_clock_source"]=="VISIBLE_MATCH_DESCRIPTION_EXPLICIT_UTC"
    assert event["explicit_visible_utc_match_quote"]=="el 6 nov 2026 a las 13:20 UTC"
    assert event["provider_player_id_equivalence_certified"] is False


def test_visible_utc_without_calendar_does_not_override_kickoff_cutoff():
    row,ui=inputs()
    ui["links"]=[x for x in ui["links"] if "calendar.google.com" not in x["url"]]
    ui["visible_text"]="Cuartos de final Dura indoor. el 6 nov 2026 a las 13:20 UTC"
    with pytest.raises(ValueError,match="PROSPECTIVE_WINDOW_CLOSED"):
        parse_visible(row,ui,DAY,datetime(2026,11,6,13,20,tzinfo=timezone.utc))


def test_conflicting_explicit_utc_and_calendar_clock_rejected():
    row,ui=inputs()
    ui["visible_text"]="Cuartos de final Dura indoor. el 6 nov 2026 a las 14:00 UTC"
    with pytest.raises(ValueError,match="GOOGLE_CALENDAR_VISIBLE_UTC_CONFLICT"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_missing_and_ambiguous_visible_utc_clock_fail_closed():
    row,ui=inputs()
    ui["links"]=[x for x in ui["links"] if "calendar.google.com" not in x["url"]]
    ui["visible_text"]="Cuartos de final Dura indoor 6 nov 2026"
    with pytest.raises(ValueError,match="MATCH_SOURCE_EXPLICIT_UTC_CLOCK_MISSING"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    ui["visible_text"]="Dura indoor el 6 nov 2026 a las 13:20 UTC; el 6 nov 2026 a las 14:00 UTC"
    with pytest.raises(ValueError,match="CONFLICTING_VISIBLE_UTC_MATCH_CLOCKS"):
        parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))


def test_visible_utc_must_match_bogota_calendar_day():
    row,ui=inputs()
    ui["links"]=[x for x in ui["links"] if "calendar.google.com" not in x["url"]]
    ui["visible_text"]="Cuartos de final Dura indoor el 5 nov 2026 a las 13:20 UTC"
    with pytest.raises(ValueError,match="KICKOFF_OUTSIDE_BOGOTA_CALENDAR_DAY"):
        parse_visible(row,ui,DAY,datetime(2026,11,4,23,tzinfo=timezone.utc))


def test_real_nov18_all_historical_candidate_ids_are_visible_to_browser_schedule():
    """Detect quietly sampling only six of the actual eligible original history pairs.

    This tests only the prospectively captured browser name-hint calendar.
    It never calls providers or admits a model row.
    """
    from tools.matrix_tennis_browser_verified_detail_capture import (
        ROOT as RESEARCH_ROOT, eligible_priorities, source
    )
    root=Path(__file__).resolve().parents[1]
    research,_=source(root,RESEARCH_ROOT/"2026-11-18/MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json")
    candidates=eligible_priorities(root,research)
    assert len(candidates)>=9, "PROSPECTIVE_CHALLENGER_HARD_CLAY_CANDIDATES_MISSING"
    assert any(any(x["surface_history_lane"]=="Clay" for x in c["original_history_pair_hints"])
               for c in candidates[6:]), "CLAY_OUTSIDE_FORMER_SIX_ITEM_CAPTURE_CAP_NOT_PROVED"
    assert len(candidates)<=12, "SCHEDULED_CAPTURE_STILL_TRUNCATES_WITHOUT_EXPLICIT_BACKLOG"
    assert len({x["sofascore_id"] for x in candidates})==len(candidates)


def test_real_visible_est_ltu_rus_flags_are_recognized_without_approving_ids():
    from tools.matrix_tennis_browser_verified_detail_capture import (
        visible_country_candidates, COUNTRY_LABELS
    )
    from tools.matrix_tennis_browser_challenger_pit_gate import COUNTRY_IOC
    for country,ioc in (("Estonia","EST"),("Lithuania","LTU"),("Russia","RUS")):
        nodes=[{"name":"","label":"","flag_alts":["Tennis Player", country]}]
        assert visible_country_candidates(nodes)==[country]
        assert country in COUNTRY_LABELS
        assert COUNTRY_IOC[country]==ioc

def test_rejected_larger_challenger_scan_preserves_exact_attempt_and_old_receipt(tmp_path):
    import hashlib,json
    import pytest
    from tools.matrix_tennis_browser_verified_detail_capture import persist_detail_capture_attempt
    base={"real_money":"BLOCKED","new_model_observations_admitted":0,
          "telegram_signal_authorized":False,
          "details_examined":10,"original_authority_pair_candidates":10,
          "individual_visible_metadata_verified_count":3,
          "status":"REJECTED_REGRESSED_DETAILS_PRESERVED",
          "blocked_reasons":[{"sofascore_id":"17561578","reason":"VISIBLE_PLAYER_COUNTRY_MISSING_OR_AMBIGUOUS"}]}
    first=persist_detail_capture_attempt(tmp_path,base)
    original=(tmp_path/"MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_LAST.json").read_bytes()
    assert hashlib.sha256(original).hexdigest()==first
    changed={**base,"status":"VERIFIED_VISIBLE_CHALLENGER_METADATA_RESEARCH_ONLY",
             "individual_visible_metadata_verified_count":6,"blocked_reasons":[]}
    second=persist_detail_capture_attempt(tmp_path,changed)
    assert second!=first
    archive=tmp_path/"archive"/("MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_"+first+".json")
    assert archive.read_bytes()==original
    assert json.loads((tmp_path/"MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_LAST.json").read_bytes())==changed
    unsafe={**base,"new_model_observations_admitted":1}
    with pytest.raises(ValueError,match="CAPTURE_ATTEMPT_MUST_BE_RESEARCH_ONLY"):
        persist_detail_capture_attempt(tmp_path,unsafe)


def test_visible_challenger_r32_dieciseisavos_is_not_silently_rejected():
    """Source label observed in 18-Nov Metz and Helsinki match-page links."""
    row,ui=inputs()
    for entry in ui["links"]:
        if "/tournament/challenger/" in entry["url"]:
            entry["name"]=entry["name"].replace("Cuartos de final","Dieciseisavos de final")
    ui["visible_text"]=ui["visible_text"].replace("Cuartos de final","Dieciseisavos de final")
    result=parse_visible(row,ui,DAY,datetime(2026,11,5,23,tzinfo=timezone.utc))
    assert result["round"]=="Dieciseisavos de final"
    assert result["surface"]=="Hard"
    assert result["provider_player_id_equivalence_certified"] is False


def test_successful_challenger_capture_preserves_prior_exact_utf8_bytes(tmp_path):
    """Never discard the original source clock when a later provider view changes."""
    import hashlib,json
    from tools.matrix_tennis_browser_verified_detail_capture import persist_versioned_details
    path=tmp_path/"sofascore_verified_match_details.json"
    old={"schema":"MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
         "real_money":"BLOCKED","new_model_observations_admitted":0,
         "telegram_signal_authorized":False,"events":[
            {"sofascore_event_id":"123","player_name":"Nicoláš",
             "kickoff_utc":"2026-11-18T15:00:00Z"}]}
    a=persist_versioned_details(path,old)
    original=path.read_bytes()
    assert a==hashlib.sha256(original).hexdigest()
    assert "Nicoláš".encode("utf-8") in original
    changed={**old,"events":[{**old["events"][0],
            "kickoff_utc":"2026-11-18T23:30:00Z"}]}
    b=persist_versioned_details(path,changed)
    assert a!=b
    previous=tmp_path/"archive"/(
        "MATRIX_TENNIS_SOURCE_DETAILS_SHA256_"+a+".json")
    assert previous.read_bytes()==original
    assert json.loads(path.read_bytes())["events"][0]["kickoff_utc"]=="2026-11-18T23:30:00Z"
    assert persist_versioned_details(path,changed)==b
    assert len(list((tmp_path/"archive").glob("MATRIX_TENNIS_SOURCE_DETAILS_SHA256_*.json")))==1
    previous.write_bytes(original+b" ")
    with pytest.raises(ValueError,match="ORIGINAL_CHALLENGER_DETAIL_ARCHIVE_TAMPER"):
        persist_versioned_details(path,old)

def test_windows_console_escape_does_not_change_utf8_evidence(tmp_path):
    import json
    from tools.matrix_tennis_browser_verified_detail_capture import persist_versioned_details
    doc={"real_money":"BLOCKED","new_model_observations_admitted":0,
         "telegram_signal_authorized":False,"events":[
            {"name":"Miloš Čilić","kickoff_utc":"2026-11-18T15:00:00Z"}]}
    path=tmp_path/"details.json"
    persist_versioned_details(path,doc)
    assert "Čilić".encode("utf-8") in path.read_bytes()
    # CLI writes escaped representation only on Windows' CP1252 stdout.
    assert json.dumps(doc,ensure_ascii=True).encode("cp1252")
