from pathlib import Path


def test_expired_paid_daily_production_is_manual_only():
    """Do not resurrect paid API polling solely to satisfy an obsolete cadence test."""
    text = Path(".github/workflows/api-football-prospective-daily-production.yml").read_text(encoding="utf-8")
    header = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in header
    assert "schedule:" not in header
    assert "push:" not in header
    assert 'cron: "1,16,31,46 * * * *"' not in text
    assert "Expired API-FOOTBALL paid entitlement: 2026-10-28." in header
    assert "manual diagnostics only" in header


def test_market_freeze_keeps_15m_cadence():
    text = Path(".github/workflows/api-football-prospective-market-freeze.yml").read_text(encoding="utf-8")
    assert 'cron: "8,23,38,53 * * * *"' in text


def test_producers_do_not_cancel_each_other_mid_cycle():
    daily = Path(".github/workflows/api-football-prospective-daily-production.yml").read_text(encoding="utf-8")
    freeze = Path(".github/workflows/api-football-prospective-market-freeze.yml").read_text(encoding="utf-8")
    assert "cancel-in-progress: false" in daily
    assert "cancel-in-progress: false" in freeze
