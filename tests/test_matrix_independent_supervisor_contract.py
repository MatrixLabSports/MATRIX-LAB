"""Offline regression contract: post-expiry independent readiness is diagnostic only.

Never sends Telegram messages, queries providers or authorizes a paid API.
"""
import json
import os
import subprocess
import sys
from datetime import date

from tools.football_subscription_deadline_guard import evaluate_independent_sources


def test_independent_readiness_is_fail_closed_after_expiry():
    result = evaluate_independent_sources(date(2026, 10, 30))
    assert result["paid_api_football_usable"] is False
    assert result["operational_telegram_without_paid_api_certified"] is False
    assert result["signal_emission_authorized_by_this_check"] is False
    assert result["real_money"] == "BLOCKED"
    assert result["automatic_wagering"] is False


def test_independent_supervisor_mode_is_offline_diagnostic():
    env = dict(os.environ)
    env.pop("MATRIX_API_FOOTBALL_AUTHORIZED", None)
    env.pop("API_FOOTBALL_KEY", None)
    env.pop("TELEGRAM_BOT_TOKEN", None)
    env["MATRIX_INDEPENDENT_SOURCE_READINESS"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "tools.telegram_green_signal_alerts"],
        env=env, capture_output=True, text=True, timeout=30, check=True,
    )
    report = json.loads(result.stdout.strip())
    assert report["api_calls_made"] == 0
    assert report["telegram_messages_sent"] == 0
    assert report["full_supervisor_certified"] is False
    assert report["real_money"] == "BLOCKED"
    assert report["automatic_wagering"] is False


def test_regular_supervisor_cannot_bypass_paid_authorization():
    env = dict(os.environ)
    env.pop("MATRIX_API_FOOTBALL_AUTHORIZED", None)
    env.pop("MATRIX_INDEPENDENT_SOURCE_READINESS", None)
    env.pop("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", None)
    result = subprocess.run(
        [sys.executable, "-m", "tools.telegram_green_signal_alerts"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "API_FOOTBALL_SUBSCRIPTION_NOT_VERIFIED_FAIL_CLOSED" in result.stderr
