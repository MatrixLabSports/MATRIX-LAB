from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_telegram_15m_supervisor_keeps_multisource_watchdog_contract():
    text = _read(".github/workflows/telegram-matrix-supervisor-15m.yml")
    required = [
        'cron: "*/15 * * * *"',
        "cancel-in-progress: false",
        "ODDS_API_NET_KEY",
        "python -m tools.telegram_green_signal_alerts",
        "python -m tools.telegram_monitoring_watchdog",
        "MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json",
        "MATRIX_TELEGRAM_MONITORING_WATCHDOG_LAST.json",
        "MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_LAST.json",
        "REAL_MONEY: BLOCKED",
        "AUTO_BETTING: DISABLED",
    ]
    missing = [item for item in required if item not in text]
    assert not missing, f"telegram 15m contract regression: {missing}"


def test_clv_watcher_cannot_be_cancelled_by_repeated_15m_triggers():
    text = _read(".github/workflows/football-clv-continuous-watcher.yml")
    assert "cancel-in-progress: false" in text
    assert "cancel-in-progress: true" not in text


def test_clv_watcher_keeps_preferred_odds_transport_and_no_new_miss_guard():
    text = _read(".github/workflows/football-clv-continuous-watcher.yml")
    required = [
        "ODDS_API_NET_KEY",
        "python -m tools.football_clv_odds_api_net_capture",
        "python -m tools.football_clv_tracking_cycle",
        "POLL_SECONDS: 90",
        "CLV_MISSED_BASELINE",
        "CLV_NO_NEW_MISSED_AFTER_KICKOFF=PASS",
        "CLV_WATCHER_HEARTBEAT_PERSISTED=PASS",
        "watcher_heartbeat.json",
        "REAL_MONEY: BLOCKED",
        "AUTO_BETTING: DISABLED",
    ]
    missing = [item for item in required if item not in text]
    assert not missing, f"CLV monitoring contract regression: {missing}"
