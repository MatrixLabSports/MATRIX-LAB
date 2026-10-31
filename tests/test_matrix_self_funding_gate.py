import json
from pathlib import Path

from tools.matrix_self_funding_gate import build


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_current_matrix_is_not_self_funded_and_bankroll_is_excluded():
    result = build(
        _load("config/MATRIX_SELF_FUNDING_POLICY.json"),
        _load("evidence/governance/MATRIX_OPERATING_CASH_LEDGER.json"),
        _load("evidence/notifications/telegram/MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_LAST.json"),
    )
    assert result["status"] == "BLOCKED_NOT_SELF_FUNDED"
    assert result["decision"]["new_recurring_infrastructure_spend_authorized_by_gate"] is False
    assert result["betting_economics_reference_only"]["counted_as_operating_revenue"] is False
    assert result["betting_economics_reference_only"]["eligible_to_pay_infrastructure"] is False
    assert result["operating_economics"]["verified_collected_operating_revenue_usd"] == 0
    assert result["operating_economics"]["minimum_reserve_target_usd"] == 327


def test_gate_opens_only_with_collected_revenue_and_reserve():
    policy = _load("config/MATRIX_SELF_FUNDING_POLICY.json")
    ledger = _load("evidence/governance/MATRIX_OPERATING_CASH_LEDGER.json")
    bankroll = _load("evidence/notifications/telegram/MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_LAST.json")
    ledger["summary"].update({
        "verified_collected_operating_revenue_usd": 500,
        "verified_operating_expenses_usd": 100,
        "verified_cash_reserve_usd": 327,
        "uncollected_invoices_usd": 9999,
    })
    result = build(policy, ledger, bankroll)
    assert result["status"] == "PASS_SELF_FUNDED"
    assert result["decision"]["new_recurring_infrastructure_spend_authorized_by_gate"] is True
    assert result["operating_economics"]["uncollected_invoices_usd"] == 9999
