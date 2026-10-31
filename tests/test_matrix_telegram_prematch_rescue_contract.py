"""Static regression contract for default-branch prematch rescue workflow.

Run with a checked-out main workflow or use GitHub Actions main-branch tests.
"""
from pathlib import Path
import pytest

P = Path(".github/workflows/telegram-prematch-rescue.yml")

@pytest.mark.skipif(not P.exists(), reason="Rescue workflow is maintained on default branch only")
def test_rescue_dependencies_and_independent_sources():
    s=P.read_text(encoding="utf-8")
    assert "python -m pip install requests pytest pillow" in s
    assert "--require-paid-use" not in s
    assert "--independent-source-readiness" in s
    assert 'test -n "$API_FOOTBALL_KEY"' not in s
    for v in ['test -n "$TELEGRAM_BOT_TOKEN"', 'test -n "$TELEGRAM_CHAT_ID"', 'test -n "$ODDS_API_NET_KEY"', 'REAL_MONEY: BLOCKED', 'AUTO_BETTING: DISABLED']:
        assert v in s, v
