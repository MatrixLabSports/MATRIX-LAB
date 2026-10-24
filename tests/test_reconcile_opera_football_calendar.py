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
