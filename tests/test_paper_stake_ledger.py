import json

import pytest

from app.research.football.paper_stake_ledger import (
    PaperStakeLedger,
    calculate_clv_gated_paper_stake,
)


def _kwargs(**changes):
    data = dict(
        fixture_id="fx-1",
        market_key="over_2_5",
        selection_key="over",
        bankroll_before=5_000_000,
        p_matrix=0.60,
        entry_odds=2.00,
        frozen_at_utc="2026-10-13T12:00:00+00:00",
        clv_state_sha256="a" * 64,
        clv_closing_observations=300,
        clv_metrics_opened=True,
        clv_positive_confirmed=True,
    )
    data.update(changes)
    return data


def test_sizing_is_blocked_while_clv_metrics_are_sealed():
    decision = calculate_clv_gated_paper_stake(
        **_kwargs(clv_closing_observations=12, clv_metrics_opened=False)
    )
    assert decision.status == "BLOCKED_CLV_METRICS_SEALED"
    assert decision.stake_calculated == 0
    assert decision.applied_bankroll_fraction == 0
    assert decision.real_money == "BLOCKED"


def test_sizing_is_blocked_without_positive_clv_confirmation():
    decision = calculate_clv_gated_paper_stake(
        **_kwargs(clv_positive_confirmed=False)
    )
    assert decision.status == "BLOCKED_CLV_NOT_POSITIVE_CONFIRMED"
    assert decision.stake_calculated == 0


def test_quarter_kelly_is_capped_to_half_percent_bankroll():
    decision = calculate_clv_gated_paper_stake(**_kwargs())
    # Full Kelly for p=.60 @2.00 is 20%; quarter Kelly would be 5%,
    # but the governed paper cap is 0.5% of bankroll.
    assert decision.full_kelly_fraction == pytest.approx(0.20)
    assert decision.requested_fractional_kelly == pytest.approx(0.25)
    assert decision.applied_bankroll_fraction == pytest.approx(0.005)
    assert decision.stake_calculated == pytest.approx(25_000)
    assert decision.status == "ELIGIBLE_PAPER_SIZING"
    assert decision.mode == "PAPER_ONLY"


def test_full_kelly_is_forbidden():
    with pytest.raises(ValueError, match="FULL_OR_EXCESSIVE_KELLY_FORBIDDEN"):
        calculate_clv_gated_paper_stake(**_kwargs(fractional_kelly=1.0))


def test_blocked_decision_cannot_enter_stake_ledger(tmp_path):
    decision = calculate_clv_gated_paper_stake(
        **_kwargs(clv_metrics_opened=False)
    )
    ledger = PaperStakeLedger(tmp_path / "stake.jsonl")
    with pytest.raises(ValueError, match="BLOCKED_SIZING_DECISION"):
        ledger.append(decision)


def test_eligible_paper_stake_is_hash_chained_and_duplicate_freeze_rejected(tmp_path):
    decision = calculate_clv_gated_paper_stake(**_kwargs())
    ledger = PaperStakeLedger(tmp_path / "stake.jsonl")
    entry = ledger.append(decision)

    rows = ledger.load(verify=True)
    assert len(rows) == 1
    assert rows[0]["entry_sha256"] == entry["entry_sha256"]
    assert len(entry["entry_sha256"]) == 64
    assert rows[0]["decision"]["real_money"] == "BLOCKED"

    with pytest.raises(ValueError, match="DUPLICATE_STAKE_FREEZE"):
        ledger.append(decision)
