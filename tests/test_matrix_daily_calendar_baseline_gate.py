from __future__ import annotations

from tools.matrix_daily_calendar_baseline_gate import BaselineGateError, validate


def report():
    browser = lambda n: {
        "count": n,
        "count_type": "AUTOMATED_BROWSER_UI_EXACT",
        "operator_manual_intervention_required": False,
        "captured_at_utc": "2026-10-06T13:00:00Z",
        "url": "https://example.test",
    }
    paid = lambda n: {
        "count": n,
        "capture_started_at_utc": "2026-10-06T13:05:00Z",
    }
    return {
        "schema": "MATRIX_DAILY_WORLD_CALENDAR_SOURCE_COUNTS_V2",
        "target_date_bogota": "2026-10-06",
        "calendar_baseline_complete": True,
        "operator_manual_intervention_required": False,
        "browser_baseline_completed_at_utc": "2026-10-06T13:01:00Z",
        "task_order": [
            "CALENDAR_BASELINE_SOFASCORE_FLASHSCORE_FIRST",
            "PAID_APIS_SECOND",
            "COVERAGE_COMPARE_AND_GAP_DETECTION_THIRD",
            "CANONICAL_RECONCILIATION_DEDUP_AND_GOVERNED_PIPELINE_FOURTH",
        ],
        "tennis": {
            "sofascore": browser(413),
            "flashscore": browser(410),
            "rapidapi_tennis": paid(250),
            "api_tennis": paid(407),
        },
        "football": {
            "sofascore": browser(220),
            "flashscore": browser(209),
            "api_football": paid(200),
        },
        "truth_rules": {
            "invented_counts_prohibited": True,
            "partial_accessibility_count_is_never_promoted_to_world_total": True,
        },
    }


def test_exact_automated_calendar_first_report_passes():
    result = validate(report())
    assert result["status"] == "PASS"
    assert result["manual_intervention_required"] is False


def test_pending_or_partial_sofascore_is_blocked():
    r = report()
    r["football"]["sofascore"]["count"] = None
    r["football"]["sofascore"]["count_type"] = "PENDING_EXACT_UI_TOTAL"
    try:
        validate(r)
    except BaselineGateError as exc:
        assert "EXACT_NUMERIC_COUNT_REQUIRED" in str(exc)
    else:
        raise AssertionError("partial source must block")


def test_user_manual_count_is_not_accepted_as_automated_baseline():
    r = report()
    r["tennis"]["flashscore"]["count_type"] = "USER_VISIBLE_UI_SCREENSHOT_VERIFIED"
    try:
        validate(r)
    except BaselineGateError as exc:
        assert "AUTOMATED_EXACT_BROWSER_PROVENANCE_REQUIRED" in str(exc)
    else:
        raise AssertionError("manual count must not satisfy autonomous baseline")


def test_paid_api_cannot_start_before_browser_baseline():
    r = report()
    r["football"]["api_football"]["capture_started_at_utc"] = "2026-10-06T12:59:00Z"
    try:
        validate(r)
    except BaselineGateError as exc:
        assert "PAID_API_STARTED_BEFORE_BROWSER_BASELINE" in str(exc)
    else:
        raise AssertionError("API-first execution must block")
