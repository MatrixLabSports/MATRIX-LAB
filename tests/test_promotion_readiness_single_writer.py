from pathlib import Path

WORKFLOWS = Path(".github/workflows")
INDIVIDUAL = [
    WORKFLOWS / "api-football-1x2-promotion-readiness.yml",
    WORKFLOWS / "api-football-under25-promotion-readiness.yml",
    WORKFLOWS / "api-football-double-chance-1x-promotion-readiness.yml",
    WORKFLOWS / "api-football-double-chance-x2-promotion-readiness.yml",
]
CONSOLIDATED = WORKFLOWS / "api-football-promotion-readiness-consolidated.yml"
GATE_PATH = "evidence/notifications/telegram/MATRIX_TELEGRAM_MULTI_MARKET_SIGNAL_GATE_LAST.json"
GATE_COMMAND = "python -m tools.telegram_multi_market_signal_gate"


def test_promotion_readiness_gate_has_exactly_one_writer():
    for path in INDIVIDUAL:
        text = path.read_text(encoding="utf-8")
        assert "contents: write" not in text, path
        assert "contents: read" in text, path
        assert GATE_PATH not in text, path
        assert GATE_COMMAND not in text, path

    text = CONSOLIDATED.read_text(encoding="utf-8")
    assert "contents: write" in text
    assert GATE_PATH in text
    assert GATE_COMMAND in text
    assert "matrix-football-promotion-readiness-single-writer" in text
    assert "cancel-in-progress: false" in text


def test_consolidated_gate_keeps_fail_closed_contract():
    text = CONSOLIDATED.read_text(encoding="utf-8")
    required = [
        "MATRIX_1X2_PROMOTION_READINESS_LAST.json",
        "MATRIX_UNDER25_PROMOTION_READINESS_LAST.json",
        "MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json",
        "MATRIX_DOUBLE_CHANCE_X2_PROMOTION_READINESS_LAST.json",
        'assert j["governance"]["real_money"]=="BLOCKED"',
        'assert j["governance"]["automatic_wagering"] is False',
        'assert j["governance"]["odds_may_not_generate_probability"] is True',
        'assert j["governance"]["p_matrix_must_exist_before_odds"] is True',
        'assert j["governance"]["no_backfill"] is True',
    ]
    for token in required:
        assert token in text, token
