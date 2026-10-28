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


def test_watchlist_uses_target_date_27oct():
    recon={
      "status":"PASS_OPEN_RECONCILIATION",
      "target_date_bogota":"2026-10-27",
      "confirmed_both":[{
        "flashscore":"Cúcuta - Águilas Doradas",
        "sofascore":"27/10/26 18:00 Cúcuta Deportivo Cúcuta Rionegro Águilas Doradas Águilas Doradas 1 2.55 X 3.20 2 2.80",
        "identity_score":1.0,
      }],
      "sofascore_only":[],
      "flashscore_only":[],
      "ambiguous":[],
    }
    out=build(recon,datetime(2026,10,27,1,30,tzinfo=timezone.utc))
    assert out["confirmed_both"][0]["kickoff_display_bogota"]=="2026-10-27T18:00:00-05:00"
    assert out["counts"]["freeze_eligible"]==0
    assert out["policy"]["real_money"]=="BLOCKED"


def test_watchlist_uses_exact_flashscore_display_time_without_freezing():
    recon={
      "status":"PASS_OPEN_RECONCILIATION",
      "target_date_bogota":"2026-10-28",
      "confirmed_both":[],
      "sofascore_only":[],
      "flashscore_only":[{"flashscore":"AC Milan - Bolonia"}],
      "ambiguous":[],
    }
    temporal={
      "schema":"MATRIX_OPERA_FLASHSCORE_TEMPORAL_CAPTURE_V1",
      "target_date_bogota":"2026-10-28",
      "observations":[{
        "flashscore_observation":"AC Milan - Bolonia",
        "displayed_times_bogota":["12:30"],
        "exact_single_display_time":True,
      }],
      "policy":{
        "exact_name_match_required":True,
        "single_time_required":True,
      },
    }
    out=build(recon,datetime(2026,10,28,3,23,tzinfo=timezone.utc),flashscore_temporal=temporal)
    row=out["flashscore_only"][0]
    assert row["kickoff_display_bogota"]=="2026-10-28T12:30:00-05:00"
    assert row["temporal_source"]=="FLASHSCORE_OPERA_EXACT_SINGLE_DISPLAY_TIME"
    assert row["eligible_for_freeze"] is False
    assert out["counts"]["flashscore_exact_single_display_time"]==1
    assert out["policy"]["no_freeze_from_single_source_time"] is True


def test_watchlist_does_not_use_flashscore_time_to_override_postponed_sofascore():
    recon={
      "status":"PASS_OPEN_RECONCILIATION",
      "target_date_bogota":"2026-10-28",
      "confirmed_both":[{
        "flashscore":"Santa Cruz RJ - Campos AA",
        "sofascore":"28/10/26 Aplazado Santa Cruz-RJ Santa Cruz-RJ Campos AA Campos 1 2.00 X 3.40 2 3.10",
        "identity_score":1.0,
      }],
      "sofascore_only":[],
      "flashscore_only":[],
      "ambiguous":[],
    }
    temporal={
      "schema":"MATRIX_OPERA_FLASHSCORE_TEMPORAL_CAPTURE_V1",
      "target_date_bogota":"2026-10-28",
      "observations":[{
        "flashscore_observation":"Santa Cruz RJ - Campos AA",
        "displayed_times_bogota":["13:00"],
        "exact_single_display_time":True,
      }],
      "policy":{
        "exact_name_match_required":True,
        "single_time_required":True,
      },
    }
    out=build(recon,datetime(2026,10,28,3,23,tzinfo=timezone.utc),flashscore_temporal=temporal)
    row=out["confirmed_both"][0]
    assert row["kickoff_display_bogota"] is None
    assert row["flashscore_display_time_bogota"]=="2026-10-28T13:00:00-05:00"
    assert row["temporal_crosscheck_status"]=="POSTPONED_CONFLICT_BLOCKED"
    assert row["eligible_for_freeze"] is False


def test_watchlist_rejects_temporal_capture_wrong_date():
    recon={
      "status":"PASS_OPEN_RECONCILIATION",
      "target_date_bogota":"2026-10-28",
      "confirmed_both":[],
      "sofascore_only":[],
      "flashscore_only":[],
      "ambiguous":[],
    }
    temporal={
      "schema":"MATRIX_OPERA_FLASHSCORE_TEMPORAL_CAPTURE_V1",
      "target_date_bogota":"2026-10-29",
      "observations":[],
      "policy":{
        "exact_name_match_required":True,
        "single_time_required":True,
      },
    }
    try:
        build(recon,datetime(2026,10,28,3,23,tzinfo=timezone.utc),flashscore_temporal=temporal)
    except ValueError as exc:
        assert str(exc)=="FLASHSCORE_TEMPORAL_TARGET_DATE_MISMATCH"
    else:
        raise AssertionError("temporal target mismatch must fail closed")
