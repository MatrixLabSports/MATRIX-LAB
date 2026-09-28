import json
from pathlib import Path

from app.market.colombia_bookmakers import (
    EXECUTION_BOOKMAKERS,
    QUARANTINED_BOOKMAKERS,
    REFERENCE_ONLY_BOOKMAKERS,
    classify_bookmaker,
)
from app.market.price_execution import StakePolicy


MANDATE_PATH = Path("evidence/audit/MATRIX_COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1.json")
DOC_PATH = Path("docs/providers/MATRIX_COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1.md")

EXPECTED_EXECUTION_KEYS = {
    "betano", "betplay", "betsson", "bwin", "codere", "luckia", "mryoker",
    "rivalo", "rushbet", "sportium", "stake", "wplay", "yajuego", "zamba",
}


def _mandate():
    return json.loads(MANDATE_PATH.read_text(encoding="utf-8"))


def test_permanent_mandate_is_active_additive_and_user_change_controlled():
    mandate = _mandate()
    assert mandate["status"] == "ACTIVE"
    assert mandate["mode"] == "PERMANENT_ADDITIVE"
    assert mandate["change_control"] == "USER_EXPLICIT_REPLACE_MODIFY_SUSPEND_REVOKE_ONLY"
    doc = DOC_PATH.read_text(encoding="utf-8")
    assert "PERMANENT + ADDITIVE" in doc
    assert "REPLACES, MODIFIES, SUSPENDS or REVOKES" in doc


def test_permanent_execution_portfolio_cannot_silently_shrink():
    mandate = _mandate()
    assert set(mandate["execution_candidates"]) == EXPECTED_EXECUTION_KEYS
    assert set(EXECUTION_BOOKMAKERS) == EXPECTED_EXECUTION_KEYS
    assert len(EXECUTION_BOOKMAKERS) == 14
    for key in EXPECTED_EXECUTION_KEYS:
        assert classify_bookmaker(key).execution_eligible is True


def test_reference_and_quarantine_books_cannot_silently_become_execution():
    mandate = _mandate()
    assert mandate["non_execution"]["pinnacle"] == "REFERENCE_ONLY_NOT_COLOMBIA_EXECUTION"
    assert "pinnacle" in REFERENCE_ONLY_BOOKMAKERS
    assert classify_bookmaker("pinnacle").execution_eligible is False

    assert "unibet" in QUARANTINED_BOOKMAKERS
    assert "bingo_casino" in QUARANTINED_BOOKMAKERS
    assert classify_bookmaker("unibet").execution_eligible is False
    assert classify_bookmaker("bingo_casino").execution_eligible is False


def test_permanent_odds_to_probability_and_activation_guards_remain_fail_closed():
    mandate = _mandate()
    inv = mandate["hard_invariants"]
    assert inv["odds_to_p_matrix"] is False
    assert inv["p_matrix_before_price_selection"] is True
    assert inv["exact_market_contract_required"] is True
    assert inv["different_lines_never_equivalent"] is True
    assert inv["unmapped_markets_fail_closed"] is True
    assert inv["automatic_wagering"] is False
    assert inv["provider_used_requires_physical_network_evidence"] is True

    activation = mandate["activation"]
    assert activation["purchase_required_now"] is False
    assert activation["physical_activation_required"] is True
    assert activation["real_money"] == "BLOCKED"


def test_permanent_minimum_odds_and_stake_gates_are_not_weakened():
    mandate = _mandate()
    inv = mandate["hard_invariants"]
    assert inv["minimum_decimal_odds_exclusive"] == 1.50
    assert inv["stake_requires_calibration_gate"] is True
    assert inv["stake_requires_real_money_gate"] is True
    assert inv["stake_is_risk_and_calibration_adjusted"] is True

    policy = StakePolicy()
    assert policy.min_decimal_odds_exclusive == 1.50
    assert policy.fractional_kelly == 0.25
    assert policy.max_bankroll_fraction == 0.02


def test_freeze_and_truthfulness_invariants_remain_permanent():
    mandate = _mandate()
    inv = mandate["hard_invariants"]
    assert inv["prematch_freeze_required"] is True
    assert inv["freeze_ledger_append_only"] is True
    assert inv["freeze_ledger_hash_chained"] is True
    assert inv["duplicate_freeze_rejected"] is True
    assert inv["architecture_ready_not_provider_active"] is True
    assert inv["provider_visible_not_regulator_authorized"] is True


def test_permanent_mandate_is_indexed_for_future_continuity():
    index = json.loads(
        Path("evidence/audit/MATRIX_PERMANENT_MANDATE_INDEX_V1.json").read_text(encoding="utf-8")
    )
    rows = {row["id"]: row for row in index["mandates"]}
    assert "COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1" in rows
    assert rows["COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1"]["status"] == "PERMANENT_ACTIVE"
    assert rows["COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1"]["path"] == (
        "docs/providers/MATRIX_COLOMBIA_BOOKMAKER_PERMANENT_MANDATE_V1.md"
    )
    assert index["continuity_requirement"].startswith("Future prompts, handoffs, audits")
