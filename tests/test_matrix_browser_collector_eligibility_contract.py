"""Regression guard for collector eligibility flags.

The collector must not label an exact quote as emitted solely because odds > 1.50.
This test checks the source contract; it is not a live bookmaker certification.
"""
from pathlib import Path


def test_collector_requires_economic_and_prematch_gates():
    src = (Path(__file__).resolve().parents[1] / "tools" / "matrix_selfhosted_browser_quote_collector.py").read_text(encoding="utf-8")
    assert 'emitted=bool(exact_found and exact_price>1.50)' not in src
    assert 'p_value*exact_price-1.0>=0.05' in src
    assert 'prematch_ok=bool(kickoff_dt is not None and now<kickoff_dt)' in src
    assert 'adapter.get("status")=="CERTIFIED_EXACT_OVER25" and economic_ok and prematch_ok' in src
    assert '"NO_SIGNAL_ECONOMIC_GATE"' in src
    assert '"NO_SIGNAL_KICKOFF"' in src
