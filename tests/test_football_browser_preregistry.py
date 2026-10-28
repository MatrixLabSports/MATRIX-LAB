from tools.football_browser_preregistry import build_browser_preregistry


def _base_watchlist():
    return {
        "status": "PASS_MONITORING_ONLY",
        "generated_at_utc": "2026-10-28T02:56:17+00:00",
        "target_date_bogota": "2026-10-28",
        "confirmed_both": [{
            "event_identity": "A - B",
            "sofascore_observation": "28/10/26 14:00 A A B B",
            "flashscore_observation": "A - B",
            "source_count": 2,
            "kickoff_display_bogota": "2026-10-28T14:00:00-05:00",
            "status": "CONFIRMED_BOTH_IDENTITY",
            "freeze_blocker": "KICKOFF_TIME_NOT_INDEPENDENTLY_CERTIFIED_BY_BOTH_SOURCES",
        }],
        "sofascore_only": [{
            "sofascore_observation": "28/10/26 Aplazado C C D D",
            "source_count": 1,
            "kickoff_display_bogota": None,
            "status": "SOFASCORE_ONLY_OPEN_RECONCILIATION",
            "freeze_blocker": "SECOND_SOURCE_IDENTITY_CONFIRMATION_REQUIRED",
        }],
        "flashscore_only": [{
            "flashscore_observation": "E - F",
            "source_count": 1,
            "kickoff_display_bogota": None,
            "status": "FLASHSCORE_ONLY_OPEN_RECONCILIATION",
            "freeze_blocker": "SOFASCORE_IDENTITY_OR_API_RECONCILIATION_REQUIRED",
        }],
        "ambiguous": [],
        "policy": {"source_order": ["SOFASCORE", "FLASHSCORE", "APIS"], "real_money": "BLOCKED"},
    }


def test_browser_preregistry_preserves_browser_union_before_api():
    out=build_browser_preregistry(_base_watchlist(), target_date="2026-10-28")
    assert out["status"]=="PASS_BROWSER_FIRST_PREREGISTRATION"
    assert out["counts"]["total_monitoring_events"]==3
    assert out["counts"]["prospective_before_displayed_kickoff"]==1
    assert out["counts"]["kickoff_not_certified"]==2
    assert all(row["eligible_for_freeze"] is False for row in out["events"])
    assert out["policy"]["browser_event_survives_api_absence"] is True
    assert out["policy"]["preregistration_does_not_create_p_matrix"] is True
    assert out["policy"]["odds_used"] is False
    assert out["policy"]["real_money"]=="BLOCKED"


def test_browser_preregistry_rejects_wrong_target_date():
    try:
        build_browser_preregistry(_base_watchlist(), target_date="2026-10-29")
    except ValueError as exc:
        assert str(exc)=="WATCHLIST_TARGET_DATE_MISMATCH"
    else:
        raise AssertionError("target mismatch must fail closed")


def test_browser_preregistry_never_relabels_post_start_as_prospective():
    w=_base_watchlist()
    w["generated_at_utc"]="2026-10-28T20:00:00+00:00"
    out=build_browser_preregistry(w,target_date="2026-10-28")
    row=out["events"][0]
    assert row["prospective_observation"] is False
    assert row["temporal_status"]=="NOT_PROSPECTIVE_AT_PREREGISTRATION"
