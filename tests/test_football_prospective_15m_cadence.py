from pathlib import Path


def test_daily_production_keeps_15m_cadence():
    text=Path(".github/workflows/api-football-prospective-daily-production.yml").read_text(encoding="utf-8")
    assert 'cron: "1,16,31,46 * * * *"' in text
    assert 'cron: "17 5,11,17,23 * * *"' not in text


def test_market_freeze_keeps_15m_cadence():
    text=Path(".github/workflows/api-football-prospective-market-freeze.yml").read_text(encoding="utf-8")
    assert 'cron: "8,23,38,53 * * * *"' in text


def test_producers_do_not_cancel_each_other_mid_cycle():
    daily=Path(".github/workflows/api-football-prospective-daily-production.yml").read_text(encoding="utf-8")
    freeze=Path(".github/workflows/api-football-prospective-market-freeze.yml").read_text(encoding="utf-8")
    assert "cancel-in-progress: false" in daily
    assert "cancel-in-progress: false" in freeze
