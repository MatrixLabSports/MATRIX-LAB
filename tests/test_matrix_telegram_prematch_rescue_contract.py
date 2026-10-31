"""Verify the default-branch rescue workflow without silently skipping checks.

The workflow lives on main; checkout main into a temporary directory or
pass MATRIX_RESCUE_WORKFLOW_PATH pointing at the actual YAML.
"""
import os
from pathlib import Path
import pytest

P = Path(os.getenv("MATRIX_RESCUE_WORKFLOW_PATH", ".github/workflows/telegram-prematch-rescue.yml"))

def test_rescue_dependencies_and_independent_sources():
    if not P.exists():
        pytest.fail(
            "RESCUE_WORKFLOW_NOT_AVAILABLE: checkout main or set "
            "MATRIX_RESCUE_WORKFLOW_PATH to the real main-branch YAML"
        )
    s=P.read_text(encoding="utf-8")
    assert "python -m pip install requests pytest pillow" in s
    assert "--require-paid-use" not in s
    assert "--independent-source-readiness" in s
    assert 'test -n "$API_FOOTBALL_KEY"' not in s
    for v in ['test -n "$TELEGRAM_BOT_TOKEN"', 'test -n "$TELEGRAM_CHAT_ID"', 'test -n "$ODDS_API_NET_KEY"', 'REAL_MONEY: BLOCKED', 'AUTO_BETTING: DISABLED']:
        assert v in s, v
