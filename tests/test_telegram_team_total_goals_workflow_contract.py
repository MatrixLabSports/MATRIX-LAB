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
    assert 'j["team_total_quote_policy"]["snapshot_type"]=="team total"' in text
    assert 'j["team_total_quote_policy"]["period"]=="full time"' in text
    assert 'j["team_total_quote_policy"]["physical_browser_fallback"] is True' in text
    assert 'j["team_total_quote_policy"]["physical_browser_max_age_seconds"]==1800' in text
    assert 'j["event_identity_policy"]["recovery_window_seconds"]==21600' in text


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
    assert '"types":"team total"' in text
    assert '"periods":"full time"' in text
    assert "EVENT_SEARCH_RECOVERY_WINDOW_SECONDS=21600" in text
    assert "physical_book_team_total_offer" in text
    assert "PHYSICAL_BOOK_QUOTE_MAX_AGE_SECONDS=1800" in text


def test_physical_team_total_capture_workflow_is_permanent_15m():
    text=Path(".github/workflows/matrix-team-total-physical-capture.yml").read_text(encoding="utf-8")
    assert 'cron: "6,21,36,51 * * * *"' in text
    assert "python -m tools.physical_team_total_browser_capture" in text
    assert "MATRIX_TEAM_TOTAL_PHYSICAL_CAPTURE_BRIDGE_LAST.json" in text
    assert "REAL_MONEY: BLOCKED" in text
    assert "AUTO_BETTING: DISABLED" in text


def test_picks_workflow_bridges_physical_captures_before_signal_generation():
    text=Path(".github/workflows/telegram-team-total-goals-picks.yml").read_text(encoding="utf-8")
    bridge=text.index("Normalize physical Team Total captures before PICKS NUEVOS")
    picks=text.index("Generate and dispatch governed PICKS NUEVOS")
    assert bridge < picks
    assert "python -m tools.physical_team_total_browser_capture" in text
    assert "tests/test_physical_team_total_browser_capture.py" in text
