from pathlib import Path

WORKFLOW = Path(".github/workflows/telegram-green-signals.yml")


def test_green_workflow_contract_is_v3_synced_and_final_window_certified():
    text = WORKFLOW.read_text(encoding="utf-8")
    required = [
        'cron: "7,22,37,52 * * * *"',
        "Enforce workflow definition parity main vs operational branch",
        "Build multi-market signal eligibility gate",
        "Build multi-market Telegram signal eligibility registry",
        "Supervisor Telegram — señales, cuotas y FINAL",
        "Certify final-window readiness from current blocker audit",
        "python -m tools.telegram_final_window_readiness",
        'assert j["schema_evolution"]["current_schema"]=="MATRIX_TELEGRAM_QUOTE_ATTEMPT_V3"',
        "MATRIX_TELEGRAM_FINAL_WINDOW_READINESS_LAST.json",
        "MATRIX_TELEGRAM_MULTI_MARKET_SIGNAL_GATE_LAST.json",
        "MATRIX_TELEGRAM_MARKET_SIGNAL_ELIGIBILITY_LAST.json",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, f"TELEGRAM_GREEN_WORKFLOW_CONTRACT_MISSING:{missing}"
    assert 'current_schema"]=="MATRIX_TELEGRAM_QUOTE_ATTEMPT_V2"' not in text


def test_final_window_readiness_is_persisted_and_rebase_allowlisted():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("MATRIX_TELEGRAM_FINAL_WINDOW_READINESS_LAST.json") >= 4
    assert "covered_by_15m_supervisor" in text
    assert "source_contract_passed" in text
    assert "WAITING_FINAL_REVALIDATION_WINDOW" in text
