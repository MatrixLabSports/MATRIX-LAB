"""Fail-closed paid transport, but independent 15-minute supervision is not paid-gated."""
from pathlib import Path

P = Path(".github/workflows/telegram-matrix-supervisor-15m.yml")

def test_15m_supervisor_independent_sources_not_paid_blocked():
    s=P.read_text(encoding="utf-8")
    assert '--require-paid-use' not in s
    assert '--independent-source-readiness' in s
    assert 'test -n "$API_FOOTBALL_KEY"' not in s

def test_15m_supervisor_safety_and_credentials_retained():
    s=P.read_text(encoding="utf-8")
    for token in ['cron: "*/15 * * * *"', 'REAL_MONEY: BLOCKED',
                  'AUTO_BETTING: DISABLED', 'MATRIX_MODE: SHADOW',
                  'test -n "$TELEGRAM_BOT_TOKEN"', 'test -n "$TELEGRAM_CHAT_ID"',
                  'test -n "$ODDS_API_NET_KEY"']:
        assert token in s, token
