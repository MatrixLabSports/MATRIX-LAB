from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY = Path("config/MATRIX_SELF_FUNDING_POLICY.json")
LEDGER = Path("evidence/governance/MATRIX_OPERATING_CASH_LEDGER.json")
BANKROLL = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_LAST.json")
OUT = Path("evidence/governance/MATRIX_SELF_FUNDING_GATE_LAST.json")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def build(policy: dict[str, Any], ledger: dict[str, Any], bankroll: dict[str, Any]) -> dict[str, Any]:
    target = policy["target_stack"]
    summary = ledger["summary"]
    monthly = float(target["projected_monthly_infrastructure_usd"])
    reserve_target = float(target["minimum_reserve_target_usd"])
    revenue = float(summary["verified_collected_operating_revenue_usd"])
    expenses = float(summary["verified_operating_expenses_usd"])
    reserve = float(summary["verified_cash_reserve_usd"])
    uncollected = float(summary.get("uncollected_invoices_usd") or 0)
    net_operating_cash = revenue - expenses

    if monthly <= 0 or reserve_target < monthly:
        raise ValueError("SELF_FUNDING_TARGET_INVALID")
    if min(revenue, expenses, reserve, uncollected) < 0:
        raise ValueError("NEGATIVE_OPERATING_LEDGER_VALUE")
    if policy["separation_rules"].get("paper_betting_pnl_is_operating_revenue") is not False:
        raise ValueError("PAPER_PNL_SEPARATION_REQUIRED")
    if policy["separation_rules"].get("paper_bankroll_may_pay_infrastructure") is not False:
        raise ValueError("BANKROLL_INFRASTRUCTURE_SEPARATION_REQUIRED")

    bankroll_summary = bankroll.get("summary") or {}
    checks = {
        "verified_collected_revenue_positive": revenue > 0,
        "net_operating_cash_covers_one_month": net_operating_cash >= monthly,
        "verified_cash_reserve_covers_minimum_months": reserve >= reserve_target,
        "paper_bankroll_excluded_from_revenue": True,
        "paper_bankroll_excluded_from_infrastructure_funding": True,
        "real_money_blocked": policy["self_funding_gate"].get("real_money") == "BLOCKED",
    }
    passed = all(checks.values())

    months_of_runway = reserve / monthly if monthly else 0.0
    return {
        "schema": "MATRIX_SELF_FUNDING_GATE_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_SELF_FUNDED" if passed else "BLOCKED_NOT_SELF_FUNDED",
        "checks": checks,
        "operating_economics": {
            "verified_collected_operating_revenue_usd": revenue,
            "verified_operating_expenses_usd": expenses,
            "net_operating_cash_usd": net_operating_cash,
            "verified_cash_reserve_usd": reserve,
            "uncollected_invoices_usd": uncollected,
            "projected_monthly_infrastructure_usd": monthly,
            "minimum_reserve_target_usd": reserve_target,
            "months_of_verified_infrastructure_runway": round(months_of_runway, 3),
        },
        "betting_economics_reference_only": {
            "currency": "COP",
            "current_paper_bankroll_cop": bankroll_summary.get("current_bankroll_cop"),
            "paper_pnl_cop": bankroll_summary.get("total_profit_cop"),
            "paper_units": bankroll_summary.get("total_units"),
            "counted_as_operating_revenue": False,
            "eligible_to_pay_infrastructure": False,
        },
        "decision": {
            "new_recurring_infrastructure_spend_authorized_by_gate": passed,
            "explicit_user_purchase_authorization_still_required": True,
            "reason": (
                "VERIFIED_OPERATING_REVENUE_AND_RESERVE_COVER_TARGET"
                if passed else
                "NO_VERIFIED_OPERATING_REVENUE_OR_RESERVE_SUFFICIENT_FOR_SELF_FUNDING"
            ),
        },
        "source_files": {
            "policy": str(POLICY),
            "operating_cash_ledger": str(LEDGER),
            "paper_bankroll": str(BANKROLL),
        },
    }


def main() -> None:
    result = build(_load(POLICY), _load(LEDGER), _load(BANKROLL))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
