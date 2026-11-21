"""Regression contract: expired paid football must not stop independent Telegram supervision."""
from pathlib import Path

WORKFLOW = Path(".github/workflows/telegram-green-signals.yml")

def test_paid_subscription_is_not_mandatory_for_independent_supervisor():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--require-paid-use" not in text
    assert "--independent-source-readiness" in text
    assert 'test -n "$API_FOOTBALL_KEY"' not in text

def test_schedule_and_shadow_controls_retained():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "7,22,37,52 * * * *"' in text
    assert "MATRIX_MODE: SHADOW" in text
    assert "REAL_MONEY: BLOCKED" in text
    assert "AUTO_BETTING: DISABLED" in text
    assert "Supervisor Telegram" in text

def test_telegram_and_odds_credentials_still_required():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'test -n "$TELEGRAM_BOT_TOKEN"' in text
    assert 'test -n "$TELEGRAM_CHAT_ID"' in text
    assert 'test -n "$ODDS_API_NET_KEY"' in text
