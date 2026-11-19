"""Workflow-level regression for legitimate source priority and research fallback.

These tests do not contact browser providers or create synthetic fixtures.
They prevent the research-only alternative path from being promoted.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/matrix-independent-d2-authentic-prospective-recovery.yml"


def test_browser_receipts_always_inspected_before_free_api_research():
    code = WORKFLOW.read_text(encoding="utf-8")
    assert code.index("old=(\"$DIR\"/MATRIX_OPERA_THREE_SOURCE_RESEARCH_RECEIPT_*.json)") < code.index(
        "Free-only authenticated football-data.org target day intake")
    assert code.index("new=(\"$DIR\"/MATRIX_FLASH_EXACT_MID_PREMATCH_RESEARCH_*.json)") < code.index(
        "Free-only authenticated football-data.org target day intake")
    assert code.count("if: steps.browser.outputs.attempted == 'true'") == 3


def test_missing_browser_never_claims_canonical_cross_source_identity():
    code = WORKFLOW.read_text(encoding="utf-8")
    assert 'echo "ready=false"' in code
    assert 'echo "attempted=true"' in code
    assert "NO_BOTH_BROWSER_RECEIPTS_FOR_TARGET" in code
    assert '"browser_first_receipt_lookup_attempted":True' in code
    assert '"fallback_research_only_due_to_missing_browser_receipts":ready!="true"' in code
    assert '"cross_provider_identity_certified":False' in code
    assert '"canonical_original_pit_certified":False' in code


def test_no_paid_api_or_real_money_activation_in_fallback():
    code = WORKFLOW.read_text(encoding="utf-8")
    assert "FOOTBALL_DATA_ORG_TOKEN" in code
    assert "API_FOOTBALL_DIRECT_KEY" not in code
    assert "REAL_MONEY: BLOCKED" in code
    assert 'AUTOMATIC_WAGERING: "false"' in code
    assert '"production_p_matrix_authorized":False' in code
    assert '"telegram_signal_authorized":False' in code
    assert '"automatic_wagering":False' in code
