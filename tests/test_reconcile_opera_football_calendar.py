from datetime import datetime, timezone
from tools.reconcile_opera_football_calendar import reconcile


def test_reconcile_is_conservative_and_does_not_force_counts():
    sofa={
      "target_date_bogota":"2026-10-25",
      "observations":[
        "25/10/26 9:30 TSG Hoffenheim Hoffenheim Bayer 04 Leverkusen Leverkusen 1 2.88 X 3.75 2 2.30",
        "25/10/26 15:00 FC Barcelona Barcelona Real Madrid Real Madrid 1 1.65 X 5.75 2 3.80",
      ],
    }
    flash={
      "target_date_bogota":"2026-10-25",
      "observations":[
        "Hoffenheim - Bayer Leverkusen",
        "Barcelona - Real Madrid",
        "Unknown A - Unknown B",
      ],
    }
    out=reconcile(sofa,flash,datetime(2026,10,24,22,30,tzinfo=timezone.utc))
    assert out["source_counts"]=={"sofascore":2,"flashscore":3}
    assert out["reconciliation"]["confirmed_both"]==2
    assert out["reconciliation"]["flashscore_only"]==1
    assert out["policy"]["no_forced_count_equality"] is True
    assert out["policy"]["time_match_certified"] is False
    assert out["policy"]["automatic_wagering"] is False
    assert out["policy"]["real_money"]=="BLOCKED"


def test_reconcile_supports_27oct_without_hardcoded_date():
    sofa={
      "target_date_bogota":"2026-10-27",
      "observations":[
        "27/10/26 18:00 Cúcuta Deportivo Cúcuta Rionegro Águilas Doradas Águilas Doradas 1 2.55 X 3.20 2 2.80",
      ],
    }
    flash={
      "target_date_bogota":"2026-10-27",
      "observations":["Cúcuta - Águilas Doradas"],
    }
    out=reconcile(sofa,flash,datetime(2026,10,27,1,30,tzinfo=timezone.utc))
    assert out["reconciliation"]["confirmed_both"]==1
    assert out["reconciliation"]["sofascore_only"]==0
    assert out["reconciliation"]["flashscore_only"]==0


def test_reconcile_never_reuses_same_sofascore_event_for_multiple_flashscore_rows():
    sofa={
      "target_date_bogota":"2026-10-28",
      "observations":[
        "28/10/26 14:30 Manchester City Man City Brighton & Hove Albion Brighton 1 1.57 X 4.33 2 4.75",
      ],
    }
    flash={
      "target_date_bogota":"2026-10-28",
      "observations":[
        "Manchester City - Brighton",
        "Man City - Brighton",
      ],
    }
    out=reconcile(sofa,flash,datetime(2026,10,28,2,40,tzinfo=timezone.utc))
    assert out["reconciliation"]["confirmed_both"]==1
    assert out["reconciliation"]["flashscore_only"]==1
    assert out["policy"]["one_to_one_identity_matching"] is True


def test_reconcile_rejects_physical_flashscore_broad_link_capture():
    sofa={
      "target_date_bogota":"2026-10-28",
      "observations":["28/10/26 12:00 A A B B"],
    }
    flash={
      "schema":"MATRIX_OPERA_FOOTBALL_CALENDAR_CAPTURE_V1",
      "source":"FLASHSCORE",
      "target_date_bogota":"2026-10-28",
      "observations":["A - B"],
    }
    try:
        reconcile(sofa,flash,datetime(2026,10,28,3,28,tzinfo=timezone.utc))
    except ValueError as exc:
        assert str(exc)=="FLASHSCORE_PHYSICAL_CAPTURE_V2_REQUIRED"
    else:
        raise AssertionError("broad-link Flashscore physical capture must fail closed")


def test_reconcile_accepts_scoped_flashscore_calendar_row_capture():
    sofa={
      "target_date_bogota":"2026-10-28",
      "observations":["28/10/26 12:00 A A B B"],
    }
    flash={
      "schema":"MATRIX_OPERA_FOOTBALL_CALENDAR_CAPTURE_V2",
      "source":"FLASHSCORE",
      "target_date_bogota":"2026-10-28",
      "observed_calendar_row_count":1,
      "observations":["A - B"],
      "excluded_non_calendar_links_count":1,
      "excluded_non_calendar_links":["A - C"],
      "row_classification":{
        "calendar_row_link_description":"¡Haga click para detalles del partido!",
        "excluded_preserved_for_audit":True,
      },
    }
    out=reconcile(sofa,flash,datetime(2026,10,28,3,28,tzinfo=timezone.utc))
    assert out["status"]=="PASS_OPEN_RECONCILIATION"
    assert out["source_counts"]["flashscore"]==1
    assert out["policy"]["flashscore_calendar_row_scope_enforced"] is True


def test_reconcile_normalizes_napoles_napoli_alias():
    sofa={
      "target_date_bogota":"2026-10-28",
      "observations":[
        "28/10/26 14:45 Monza Monza SSC Napoli Napoli 1 4.33 X 3.90 2 1.75",
      ],
    }
    flash={
      "target_date_bogota":"2026-10-28",
      "observations":["Monza - Nápoles"],
    }
    out=reconcile(sofa,flash,datetime(2026,10,28,3,30,tzinfo=timezone.utc))
    assert out["reconciliation"]["confirmed_both"]==1
    assert out["reconciliation"]["sofascore_only"]==0
    assert out["reconciliation"]["flashscore_only"]==0
