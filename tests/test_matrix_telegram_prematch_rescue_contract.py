"""Check the main-only rescue workflow when its file is available locally.

Operational branch intentionally does not contain the main-only workflow.
"""
from pathlib import Path
import pytest

P = Path(".github/workflows/telegram-prematch-rescue.yml")

@pytest.mark.skipif(not P.exists(), reason="Main-only rescue workflow: run test on main to certify")
def test_rescue_dependencies_and_independent_sources():
    s=P.read_text(encoding="utf-8")
    assert "python -m pip install requests pytest pillow" in s
    assert "--require-paid-use" not in s
    assert "--independent-source-readiness" in s
    assert 'test -n "$API_FOOTBALL_KEY"' not in s
    for v in ['test -n "$TELEGRAM_BOT_TOKEN"', 'test -n "$TELEGRAM_CHAT_ID"', 'test -n "$ODDS_API_NET_KEY"', 'REAL_MONEY: BLOCKED', 'AUTO_BETTING: DISABLED']:
        assert v in s, v
