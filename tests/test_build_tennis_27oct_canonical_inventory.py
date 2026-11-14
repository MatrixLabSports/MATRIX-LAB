from datetime import datetime, timezone

from tools.build_tennis_27oct_canonical_inventory import build_canonical_inventory

def _event(mid, p1, p2, start, surface="Hard", detail="ATP_CHALLENGER", fmt="SINGLES", status=""):
    return {
        "source_event_id": f"rapid:{mid}",
        "match_id": str(mid),
        "player1": {"id": "1", "name": p1},
        "player2": {"id": "2", "name": p2},
        "event_start_utc": start,
        "event_start_bogota": start,
        "surface": surface,
        "event_format": fmt,
        "provider_status": status,
        "model_derivation": {"domain_candidate": detail == "ATP_CHALLENGER" and fmt == "SINGLES" and "hard" in surface.lower()},
    }

def test_hard_requires_browser_first_for_cor_candidate():
    recon = {
        "target_date_bogota": "2026-10-27",
        "confirmed_both": [{"flashscore": "Player One - Player Two"}],
        "sofascore_only": [], "flashscore_only": [], "ambiguous": [],
    }
    rapid = {
        "target_date_bogota": "2026-10-27",
        "provider_inventory_complete": True,
        "world_calendar_inventory_count": 1,
        "events": [_event(1, "Player One", "Player Two", "2026-10-27T15:00:00+00:00")],
    }
    out = build_canonical_inventory(recon, rapid, as_of_utc="2026-10-27T03:00:00+00:00")
    row = out["rows"][0]
    assert row["canonical_status"] == "ELIGIBLE_HARD"
    assert row["browser_match_status"] == "CONFIRMED_BOTH"
    assert row["cor0203_preregister_candidate"] is True
    assert out["governance"]["automatic_model_feed"] is False
    assert out["governance"]["real_money"] == "BLOCKED"

def test_clay_and_doubles_classification():
    recon = {"target_date_bogota": "2026-10-27", "confirmed_both": [], "sofascore_only": [], "flashscore_only": [], "ambiguous": []}
    rapid = {
        "target_date_bogota": "2026-10-27",
        "provider_inventory_complete": True,
        "world_calendar_inventory_count": 2,
        "events": [
            _event(2, "Clay One", "Clay Two", "2026-10-27T15:00:00+00:00", surface="Clay", detail="OTHER"),
            _event(3, "A/B", "C/D", "2026-10-27T16:00:00+00:00", surface="Hard", detail="OTHER", fmt="DOUBLES"),
        ],
    }
    out = build_canonical_inventory(recon, rapid, as_of_utc="2026-10-27T03:00:00+00:00")
    assert out["rows"][0]["canonical_status"] == "ELIGIBLE_CLAY"
    assert out["rows"][1]["canonical_status"] == "OUT_OF_DOMAIN"

def test_post_start_is_live_only_and_browser_only_is_preserved():
    recon = {
        "target_date_bogota": "2026-10-27",
        "confirmed_both": [],
        "sofascore_only": [{"sofascore": "27/10/26 10:00 Missing A Missing B"}],
        "flashscore_only": [], "ambiguous": [],
    }
    rapid = {
        "target_date_bogota": "2026-10-27",
        "provider_inventory_complete": True,
        "world_calendar_inventory_count": 1,
        "events": [_event(4, "Live One", "Live Two", "2026-10-27T02:00:00+00:00", status="Live")],
    }
    out = build_canonical_inventory(recon, rapid, as_of_utc="2026-10-27T03:00:00+00:00")
    statuses = [x["canonical_status"] for x in out["rows"]]
    assert "LIVE_ONLY" in statuses
    assert "START_NOT_CERTIFIED" in statuses
    assert out["governance"]["post_start_backfill_forbidden"] is True

def test_cancelled_browser_row_is_never_eligible():
    recon = {
        "target_date_bogota": "2026-10-27",
        "confirmed_both": [],
        "sofascore_only": [{"sofascore": "27/10/26 Cancelado A. Player B. Player"}],
        "flashscore_only": [], "ambiguous": [],
    }
    rapid = {
        "target_date_bogota": "2026-10-27",
        "provider_inventory_complete": True,
        "world_calendar_inventory_count": 0,
        "events": [],
    }
    out = build_canonical_inventory(recon, rapid, as_of_utc="2026-10-27T03:00:00+00:00")
    assert out["rows"][0]["canonical_status"] == "CANCELLED"
    assert out["rows"][0]["cor0203_preregister_candidate"] is False
