import json
from pathlib import Path


TENNIS = Path("config/MATRIX_TENNIS_SUBSCRIPTION_DEADLINE.json")
FOOTBALL = Path("config/MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE.json")
WORKFLOW = Path(".github/workflows/paid-api-priority-review-15min.yml")


def test_both_paid_providers_are_governed_at_15_minutes():
    t = json.loads(TENNIS.read_text(encoding="utf-8"))
    f = json.loads(FOOTBALL.read_text(encoding="utf-8"))
    assert t["paid_primary"]["review_interval_minutes"] == 15
    assert f["paid_primary"]["review_interval_minutes"] == 15
    assert t["paid_primary"]["minimum_network_refresh_minutes"] == 60
    assert f["paid_primary"]["minimum_network_refresh_minutes"] == 60
    assert t["paid_primary"]["paid_through_bogota_date"] == "2026-10-28"
    assert f["paid_primary"]["paid_through_bogota_date"] == "2026-10-28"
    assert t["paid_primary"]["renewal_authorized"] is False
    assert f["paid_primary"]["renewal_authorized"] is False


def test_workflow_schedule_is_every_15_minutes_and_fail_closed_policy_is_present():
    raw = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "*/15 * * * *"' in raw
    assert 'PAID_WINDOW_CLOSED_NO_NETWORK_CALLS' in raw
    assert 'BROWSER_FIRST_GATE_PASS' in raw
    assert 'FRESH_UNDER_60M' in raw
    assert "steps.refresh.outputs.tennis_due == 'true'" in raw
    assert "steps.refresh.outputs.football_due == 'true'" in raw
    assert 'no_duplicate_persistence' in raw
    assert 'REAL_MONEY: BLOCKED' in raw
    assert 'AUTO_BETTING: DISABLED' in raw
    assert 'cancel-in-progress: false' in raw
    assert 'QUOTA_LEDGER_SEEDED_IN_TMP_ONLY' in raw
    assert "if: steps.window.outputs.active == 'true' && (steps.refresh.outputs.tennis_due == 'true' || steps.refresh.outputs.football_due == 'true')" in raw


def test_source_order_remains_browser_first():
    t = json.loads(TENNIS.read_text(encoding="utf-8"))
    f = json.loads(FOOTBALL.read_text(encoding="utf-8"))
    assert t["source_order"][:2] == ["SofaScore", "Flashscore"]
    assert f["source_order"][:2] == ["SofaScore", "Flashscore"]
