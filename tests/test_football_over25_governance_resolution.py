from pathlib import Path

from tools.football_daily_governed_over25 import resolve_over25_signal_governance
from tools.telegram_green_signal_alerts import over25_signal_governance_authorized


def test_market_scoped_over25_signal_promotion_resolves_legacy_sport_wide_false():
    resolved = resolve_over25_signal_governance(Path("."))

    assert resolved["signal_generation_authorized"] is True
    assert (
        resolved["authoritative_market_scoped_status"]
        == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
    )
    # This is intentional, not a contradiction: the legacy boolean remains
    # authoritative only for sport-wide/real-money scope.
    assert resolved["legacy_sport_wide_engine_promoted"] is False
    assert resolved["legacy_sport_wide_gate_scope"] == "SPORT_WIDE_OR_REAL_MONEY"
    assert resolved["market_scoped_scope"] == "SIGNAL_GENERATION_ONLY"
    assert resolved["automatic_wagering"] is False
    assert resolved["real_money"] == "BLOCKED"
    assert resolved["blockers"] == []


def test_telegram_uses_same_market_scoped_signal_authority_fail_closed():
    authorized, audit = over25_signal_governance_authorized()

    assert authorized is True
    assert (
        audit["promotion_status"]
        == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
    )
    assert all(audit["checks"].values())
    assert audit["real_money"] == "BLOCKED"
