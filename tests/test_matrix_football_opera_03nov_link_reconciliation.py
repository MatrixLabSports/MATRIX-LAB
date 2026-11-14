"""No fabricated fixtures, scores, odds or Telegram signals from browser links."""
from copy import deepcopy
import pytest

from tools.matrix_football_opera_03nov_link_reconciliation import reconcile


def sources():
    safe = {
        "full_world_schedule_certified": False,
        "unique_fixtures_cross_source_certified": False,
        "clock_utc_certified": False,
        "calibrated_probability_authorized": False,
        "market_quotes_certified": False,
        "telegram_signal_authorized": False,
        "model_calibration_changed": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    sofa = {
        "schema": "MATRIX_20261103_OPERA_SOFASCORE_LINK_CAPTURE_V1",
        "source": "SOFASCORE",
        "target_date_bogota": "2026-11-03",
        "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
        "source_page_url": "https://www.sofascore.com/es/football/2026-11-03",
        "distinct_observed_match_urls": 2,
        "unique_sofascore_event_ids": 2,
        "explicit_target_date_labels": 2,
        "explicit_date_with_visible_clock": 1,
        "explicit_date_without_visible_clock": 1,
        "without_explicit_target_date": 0,
        "governance": deepcopy(safe),
        "observations": [
            {
                "display_name": "3/11/26 15:00 Team Alpha Team Beta",
                "source_url":
                    "https://www.sofascore.com/es/football/match/team-alpha-team-beta/abcd#id:123",
                "source_event_id": "123",
                "explicit_target_date_label": True,
                "visible_kickoff_clock": True,
            },
            {
                "display_name": "3/11/26 Aplazado Club Delta Club Gamma",
                "source_url":
                    "https://www.sofascore.com/es/football/match/club-delta-club-gamma/x#id:124",
                "source_event_id": "124",
                "explicit_target_date_label": True,
                "visible_kickoff_clock": False,
            },
        ],
    }
    flash = {
        "schema": "MATRIX_20261103_OPERA_FLASHSCORE_LINK_CAPTURE_V1",
        "source": "FLASHSCORE",
        "target_date_bogota": "2026-11-03",
        "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
        "source_page_url": "https://www.flashscore.co/",
        "date_selector_accessibility_label": "martes, 3 de noviembre de 2026",
        "individual_fixture_date_certified": False,
        "distinct_observed_match_urls": 2,
        "governance": deepcopy(safe),
        "observations": [
            {
                "display_name": "Team Alpha - Team Beta",
                "source_url":
                    "https://www.flashscore.co/partido/futbol/team-alpha-ABCDEFGH/team-beta-ZYXWVUTS/?mid=234",
            },
            {
                "display_name": "Delta - Gamma",
                "source_url":
                    "https://www.flashscore.co/partido/futbol/club-delta-ABCDEFGH/club-gamma-ZYXWVUTS/?mid=235",
            },
        ],
    }
    return sofa, flash


def test_date_only_football_is_preserved_not_promoted():
    sofa, flash = sources()
    r = reconcile(sofa, flash)
    assert r["sofascore_counts"]["observed_urls"] == 2
    assert r["sofascore_counts"]["date_without_visible_clock"] == 1
    assert r["sofascore_counts"]["date_without_visible_clock_event_ids"] == ["124"]
    assert r["one_to_one_link_identity_candidate_count"] == 1
    assert r["one_to_one_link_identity_candidates"][0]["sofascore_event_id"] == "123"
    assert r["one_to_one_link_identity_candidates"][0]["fixture_certified"] is False
    assert r["exact_odds_verified"] is False
    assert r["telegram_signals_authorized"] is False
    assert r["real_money"] == "BLOCKED"


def test_corrupted_sofascore_date_is_rejected():
    sofa, flash = sources()
    sofa["observations"][0]["display_name"] = "2/11/26 15:00 Team Alpha Team Beta"
    with pytest.raises(ValueError, match="SOFA_DATE_FLAG_WRONG"):
        reconcile(sofa, flash)


def test_duplicate_event_id_is_rejected():
    sofa, flash = sources()
    sofa["observations"][1]["source_event_id"] = "123"
    sofa["observations"][1]["source_url"] = (
        "https://www.sofascore.com/es/football/match/club-delta-club-gamma/x#id:123"
    )
    with pytest.raises(ValueError, match="SOFA_DUPLICATE_LINK_OR_EVENT"):
        reconcile(sofa, flash)


def test_wrong_flashscore_day_rejected():
    sofa, flash = sources()
    flash["date_selector_accessibility_label"] = "lunes, 2 de noviembre de 2026"
    with pytest.raises(ValueError, match="FLASH_CALENDAR_DATE_CONTEXT_INVALID"):
        reconcile(sofa, flash)


def test_unauthorized_model_or_money_rejected():
    sofa, flash = sources()
    sofa["governance"]["real_money"] = "ENABLED"
    with pytest.raises(ValueError, match="REAL_MONEY_NOT_BLOCKED"):
        reconcile(sofa, flash)
    sofa["governance"]["real_money"] = "BLOCKED"
    flash["governance"]["calibrated_probability_authorized"] = True
    with pytest.raises(ValueError, match="GOVERNANCE_GATE_UNSAFE"):
        reconcile(sofa, flash)


def test_multiple_flash_url_variations_are_ambiguous():
    sofa, flash = sources()
    another = deepcopy(flash["observations"][0])
    another["source_url"] = another["source_url"].replace("?mid=234", "?mid=987")
    flash["observations"].append(another)
    flash["distinct_observed_match_urls"] += 1
    r = reconcile(sofa, flash)
    assert r["candidate_pair_count_before_one_to_one_filter"] == 2
    assert r["one_to_one_link_identity_candidate_count"] == 0
    assert r["ambiguous_link_pair_count"] == 2
    assert r["telegram_signals_authorized"] is False


def test_unmatched_team_name_does_not_force_cross_provider_identity():
    sofa, flash = sources()
    flash["observations"][0]["source_url"] = (
        "https://www.flashscore.co/partido/futbol/team-alpha-ABCDEFGH/"
        "other-team-ZYXWVUTS/?mid=234"
    )
    r = reconcile(sofa, flash)
    assert r["one_to_one_link_identity_candidate_count"] == 0
    assert r["status"] == "LINK_IDENTITY_CANDIDATES_ONLY_NOT_CERTIFIED_FIXTURES"


def test_invalid_undated_fixture_flag_rejected():
    sofa, flash = sources()
    sofa["observations"][1]["display_name"] = "En Vivo Club Delta Club Gamma"
    with pytest.raises(ValueError, match="SOFA_DATE_FLAG_WRONG"):
        reconcile(sofa, flash)


def test_tampered_counts_rejected():
    sofa, flash = sources()
    flash["distinct_observed_match_urls"] += 1
    with pytest.raises(ValueError, match="FLASH_COUNT_MISMATCH"):
        reconcile(sofa, flash)
