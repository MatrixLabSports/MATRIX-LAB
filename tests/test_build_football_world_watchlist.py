from datetime import datetime, timezone
from tools.build_football_world_watchlist import build


def test_watchlist_monitors_but_does_not_freeze_uncertified_time():
    recon={
      "status":"PASS_OPEN_RECONCILIATION",
      "target_date_bogota":"2026-10-25",
      "confirmed_both":[{
        "flashscore":"Hoffenheim - Bayer Leverkusen",
        "sofascore":"25/10/26 9:30 TSG Hoffenheim Hoffenheim Bayer 04 Leverkusen Leverkusen 1 2.88 X 3.75 2 2.30",
        "identity_score":1.0,
      }],
      "sofascore_only":[{"sofascore":"25/10/26 14:00 A A B B"}],
      "flashscore_only":[{"flashscore":"C - D"}],
      "ambiguous":[{"flashscore":"E - F"}],
    }
    out=build(recon,datetime(2026,10,24,22,50,tzinfo=timezone.utc))
    assert out["counts"]["confirmed_both"]==1
    assert out["counts"]["monitoring_total"]==4
    assert out["counts"]["freeze_eligible"]==0
    assert out["confirmed_both"][0]["kickoff_display_bogota"]=="2026-10-25T09:30:00-05:00"
    assert out["confirmed_both"][0]["eligible_for_monitoring"] is True
    assert out["confirmed_both"][0]["eligible_for_freeze"] is False
    assert out["policy"]["source_order"]==["SOFASCORE","FLASHSCORE","APIS"]
    assert out["policy"]["real_money"]=="BLOCKED"
