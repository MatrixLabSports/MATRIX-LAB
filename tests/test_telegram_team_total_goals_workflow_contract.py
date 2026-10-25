from pathlib import Path


def test_team_total_goals_picks_workflow_is_permanent_15m():
    p=Path(".github/workflows/telegram-team-total-goals-picks.yml")
    text=p.read_text(encoding="utf-8")
    assert 'cron: "9,24,39,54 * * * *"' in text
    assert "python -m tools.telegram_team_total_goals_picks" in text
    assert "MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_LEDGER.json" in text
    assert "MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_LAST.json" in text
    assert "REAL_MONEY: BLOCKED" in text
    assert "AUTO_BETTING: DISABLED" in text


def test_existing_green_signal_workflow_remains_15m():
    text=Path(".github/workflows/telegram-green-signals.yml").read_text(encoding="utf-8")
    assert 'cron: "7,22,37,52 * * * *"' in text


def test_new_picks_source_code_is_present():
    assert Path("tools/telegram_team_total_goals_picks.py").exists()
    text=Path("tools/telegram_team_total_goals_picks.py").read_text(encoding="utf-8")
    assert "PICKS NUEVOS MATRIX" in text
    assert "MIN_P=0.60" in text
    assert "MIN_EV=0.05" in text
    assert "MIN_ODDS=1.50" in text
    assert 'real_money":"BLOCKED"' in text
