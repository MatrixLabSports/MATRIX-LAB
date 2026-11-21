"""Research-only browser identity candidate contracts."""
import pytest

from tools.matrix_football_authorized_dual_browser_research import reconcile

HASH_A = "a"*64
HASH_B = "b"*64
DAY = "2026-11-17"


def captures():
    s = {
        "schema": "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1",
        "source": "SOFASCORE", "real_money": "BLOCKED",
        "canonical_prematch_inputs_authorized": False,
        "target_date_bogota": DAY, "captured_at_utc": "2026-11-17T02:15:00+00:00",
        "observed_link_count": 1,
        "links": [{"visible_name": "17/11/26\n18:30\nAtl. Nacional\nOnce Caldas",
                   "sofascore_event_id": "17510119", "url": "https://www.sofascore.com/es/football/match/test#id:17510119"}],
    }
    f = {
        "schema": "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1",
        "source": "FLASHSCORE", "real_money": "BLOCKED",
        "canonical_prematch_inputs_authorized": False,
        "date_evidence_mode": "RELATIVE_TOMORROW_PAGE_TITLE_ONLY_NOT_ABSOLUTE",
        "target_date_bogota": DAY, "captured_at_utc": "2026-11-17T02:16:00+00:00",
        "observed_link_count": 1,
        "links": [{"visible_name": "Atl. Nacional - Once Caldas", "flashscore_mid": "0Q6piEZ2",
                   "url": "https://www.flashscore.co/partido/futbol/test/?mid=0Q6piEZ2"}],
    }
    return s, f


def audit(s, f):
    return reconcile(s, f, sofa_sha=HASH_A, flash_sha=HASH_B)


def test_two_authorized_links_form_research_candidate_not_model_probability():
    s,f=captures()
    out=audit(s,f)
    assert out["research_candidate_count"] == 1
    assert out["strict_three_source_crosswalk_count"] == 0
    assert out["source_sha256"] == {"sofascore": HASH_A, "flashscore": HASH_B}
    row=out["research_candidates"][0]
    assert row["sofascore_event_id"] == "17510119"
    assert row["flashscore_mid"] == "0Q6piEZ2"
    assert row["source_provider_fixture_id"] is None
    assert row["cross_provider_identity_certified"] is False
    assert row["model_probability_authorized"] is False
    assert out["production_p_matrix_authorized"] is False
    assert out["real_money"] == "BLOCKED"


def test_conflicting_names_are_never_fuzzily_matched():
    s,f=captures()
    f["links"][0]["visible_name"] = "Atl. Nacional - Different Team"
    assert audit(s,f)["research_candidate_count"] == 0


def test_date_disagreement_fails_closed():
    s,f=captures()
    f["target_date_bogota"] = "2026-11-18"
    with pytest.raises(ValueError,match="TARGET_DAY_MISMATCH"):
        audit(s,f)


def test_ambiguous_same_team_pair_rejected_as_nonunique():
    s,f=captures()
    f["links"].append({**f["links"][0],"flashscore_mid":"Aa12Bb34"})
    out=audit(s,f)
    assert out["research_candidate_count"] == 0
    assert out["ambiguous_name_pair_count"] == 1


def test_untrusted_calendar_without_date_evidence_rejected():
    s,f=captures()
    f["date_evidence_mode"] = None
    with pytest.raises(ValueError,match="FLASH_DATE_EVIDENCE_NOT_RECORDED"):
        audit(s,f)


def test_no_original_pit_no_probabilities_even_if_names_equal():
    s,f=captures()
    out=audit(s,f)
    assert not out["canonical_prematch_inputs_authorized"]
    assert not out["production_p_matrix_authorized"]
    assert not out["telegram_signal_authorized"]
