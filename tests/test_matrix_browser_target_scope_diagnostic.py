"""Protect the distinction between page capture and eligible prematch price targets."""
from pathlib import Path

def test_collector_exposes_no_target_state_without_authorizing_signals():
    source = Path("tools/matrix_selfhosted_browser_quote_collector.py").read_text(encoding="utf-8")
    assert '"NO_ELIGIBLE_PREMATCH_TARGETS"' in source
    assert '"RESEARCH_ONLY_TARGETS_NO_PRODUCTION_AUTHORIZATION"' in source
    assert '"CANONICAL_CANDIDATES_PRESENT_REQUIRE_INDEPENDENT_QUOTE_GATES"' in source
    assert '"page_capture_alone_never_proves_quote_availability": True' in source
    assert '"telegram_signal_authorized": False' in source
    assert '"real_money": "BLOCKED"' in source

def test_collector_remains_python_syntax_valid():
    source = Path("tools/matrix_selfhosted_browser_quote_collector.py").read_text(encoding="utf-8")
    compile(source, "tools/matrix_selfhosted_browser_quote_collector.py", "exec")
