from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CLV = ROOT / ".github/workflows/football-clv-continuous-watcher.yml"
TELEGRAM = ROOT / ".github/workflows/telegram-green-signals.yml"
TRACKER = ROOT / "tools/football_clv_tracking_cycle.py"


def _text(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"MISSING_FILE:{path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"{label}=PASS")


def check_clv() -> None:
    w = _text(CLV)
    t = _text(TRACKER)

    cycle = w.index('echo "CLV_WATCH_CYCLE=$cycle')
    refresh = w.index("git fetch origin repair/cor09-world-pipeline", cycle)
    rebase = w.index("git rebase --autostash origin/repair/cor09-world-pipeline", cycle)
    capture = w.index("PYTHONPATH=. python -m tools.football_clv_tracking_cycle", cycle)

    require("CLV_WATCHER_STARTUP_COVERAGE_CONTRACT", "Verify startup coverage and per-cycle refresh contract" in w)
    require("CLV_WATCHER_PER_CYCLE_REFRESH_ORDER", cycle < refresh < rebase < capture)
    require("CLV_WATCHER_OPERATIONAL_REFRESH", "CLV_WATCHER_OPERATIONAL_REFRESH=PASS" in w and "CLV_WATCHER_OPERATIONAL_REFRESH=FAIL" in w)
    require("CLV_OPTION_B_PINNACLE_STRICT_FRESH_120S", "max_provider_quote_age_seconds" in w and "==120" in w)
    for field in (
        "attempted_at_utc",
        "provider_quote_updated_at_utc",
        "provider_quote_age_seconds",
        "gate_excess_seconds",
    ):
        require(f"CLV_TELEMETRY_FIELD_{field.upper()}", f'"{field}"' in t)
    require("CLV_ATTEMPT_LOG_APPEND_PATH", "closing_attempts.jsonl" in t and '"a"' in t)
    require("CLV_CONTINUOUS_WATCHER_FINAL_GATE", "CLV_CONTINUOUS_WATCHER_FINAL_GATE: PASS" in w)


def check_telegram() -> None:
    w = _text(TELEGRAM)
    require("TELEGRAM_OPERATIONAL_BRANCH_CHECKOUT", "ref: repair/cor09-world-pipeline" in w)
    require("TELEGRAM_REAL_MONEY_BLOCKED", "REAL_MONEY: BLOCKED" in w)
    require("TELEGRAM_AUTO_BETTING_DISABLED", "AUTO_BETTING: DISABLED" in w)
    require("TELEGRAM_PAPER_BANKROLL_ENABLED", "PAPER_BANKROLL: ENABLED" in w)
    require("TELEGRAM_SHARP_GATE_TEST", "tests/test_telegram_sharp_reference_gate.py" in w)
    require("TELEGRAM_SHARP_CONSENSUS_TEST", "tests/test_football_sharp_consensus.py" in w)
    require("TELEGRAM_MONITORING_WATCHDOG_TEST", "tests/test_telegram_monitoring_watchdog.py" in w)
    require("TELEGRAM_QUOTE_RECOVERY_TEST", "tests/test_telegram_quote_recovery_window.py" in w)
    require("TELEGRAM_LEDGER_PERSISTENCE", "MATRIX_TELEGRAM_SIGNAL_LEDGER.json" in w)
    require("TELEGRAM_CORRELATED_RISK_PERSISTENCE", "MATRIX_CORRELATED_RISK_CALIBRATION_LAST.json" in w)
    require("TELEGRAM_BLOCKER_AUDIT_PERSISTENCE", "MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json" in w)


def main() -> None:
    check_clv()
    check_telegram()
    print("MATRIX_WORKFLOW_REGRESSION_CONTRACTS=PASS")


if __name__ == "__main__":
    main()
