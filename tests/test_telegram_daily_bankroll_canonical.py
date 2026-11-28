import json
from pathlib import Path

from tools.telegram_daily_bankroll_canonical import build


def current_ledger():
    return json.loads(Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json").read_text())


def test_current_ledger_reconciles_to_canonical_table():
    out=build(current_ledger())
    assert out["summary"]["status"]=="PASS"
    assert out["summary"]["current_bankroll_cop"]==out["summary"]["ledger_current_bankroll_cop"]


def test_daily_bankroll_continuity_is_unbroken():
    rows=build(current_ledger())["rows"]
    for a,b in zip(rows,rows[1:]):
        assert a["bankroll_closing_cop"]==b["bankroll_opening_cop"]


def test_zero_activity_days_are_preserved():
    rows={r["date_bogota"]:r for r in build(current_ledger())["rows"]}
    assert "2026-10-16" in rows
    assert rows["2026-10-16"]["signals"]==0
    assert rows["2026-10-16"]["profit_cop"]==0


def test_day_classification_reconciles():
    for r in build(current_ledger())["rows"]:
        assert r["signals"] == (
            r["effective_settled"]+r["voids"]+r["cancelled_no_bet"]+
            r["excluded_canonical_audit"]+r["open"]
        )


def test_current_known_ledger_final_is_not_silently_rewritten():
    ledger=current_ledger()
    out=build(ledger)
    assert out["rows"][-1]["bankroll_closing_cop"]==ledger["paper_bankroll"]["current_cop"]
