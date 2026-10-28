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
