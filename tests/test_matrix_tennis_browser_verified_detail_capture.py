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
