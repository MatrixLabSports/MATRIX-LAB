from datetime import datetime, timezone

from tools.reconcile_opera_tennis_calendar import reconcile

def test_tennis_reconcile_is_one_to_one_conservative_and_fail_closed():
    sofa = {
        "target_date_bogota": "2026-10-27",
        "coverage_claim": "BROWSER_ACCESSIBILITY_TREE_OBSERVED_ONLY",
        "observations": [
            "27/10/26 8:40 Russia K. Khachanov Spain C. Alcaraz 1 4.50 2 1.20",
            "27/10/26 20:30 Kazakhstan E. Rybakina R16P2",
        ],
    }
    flash = {
        "target_date_bogota": "2026-10-27",
        "coverage_claim": "BROWSER_TOMORROW_PAGE_OBSERVED_ONLY",
        "observations": [
            "Khachanov K. - Alcaraz C.",
            "Khachanov K. - Alcaraz C.",
            "Unknown A. - Unknown B.",
        ],
    }
    out = reconcile(sofa, flash, datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc))
    assert out["source_counts"] == {"sofascore": 2, "flashscore": 2}
    assert out["reconciliation"]["confirmed_both"] == 1
    assert out["reconciliation"]["sofascore_only"] == 1
    assert out["reconciliation"]["flashscore_only"] == 1
    assert out["policy"]["one_to_one_identity_matching"] is True
    assert out["policy"]["time_match_certified"] is False
    assert out["policy"]["odds_generate_p_matrix"] is False
    assert out["policy"]["post_start_backfill_forbidden"] is True
    assert out["policy"]["automatic_wagering"] is False
    assert out["policy"]["real_money"] == "BLOCKED"

def test_tennis_reconcile_handles_accents_doubles_and_partial_names():
    sofa = {
        "target_date_bogota": "2026-10-27",
        "observations": [
            "27/10/26 0:20 Croatia A. Ružić USA C. Liu 1 2.00 2 1.80",
            "27/10/26 20:30 Dabrowski G / Stefani L Bucsa C / Fernandez L 1 1.30 2 3.40",
        ],
    }
    flash = {
        "target_date_bogota": "2026-10-27",
        "observations": [
            "Ruzic A. - Liu C.",
            "Dabrowski G./Stefani L. - Bucsa C./Fernández Leylah",
        ],
    }
    out = reconcile(sofa, flash, datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc))
    assert out["reconciliation"]["confirmed_both"] == 2
    assert out["reconciliation"]["ambiguous"] == 0
    assert out["capture_coverage"]["world_complete_certified"] is False
