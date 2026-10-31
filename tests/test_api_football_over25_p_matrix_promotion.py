from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_over25_p_matrix_promotion import (
    ENGINE_ID,
    EXPECTED_GOVERNED_ROWS,
    EXPECTED_PARAMS,
    EXPECTED_READY_INPUTS,
    build_market_scoped_promotion,
)


def test_over25_market_scoped_p_matrix_promotion_passes_current_evidence():
    promotion, matrix = build_market_scoped_promotion(
        Path("."),
        generated_at=datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc),
    )

    assert promotion["promotion_status"] == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
    assert promotion["engine_executable_for_p_matrix"] is True
    assert promotion["governed_p_matrix_engine_available"] is True
    assert promotion["frozen_parameters"] == EXPECTED_PARAMS
    assert promotion["parameter_refit_performed"] is False
    assert promotion["parameter_search_performed"] is False
    assert promotion["other_markets"]["1X2"] == "NOT_PROMOTED_BY_THIS_GATE"
    assert promotion["other_markets"]["BTTS"] == "NO_GO"
    assert promotion["protections"]["automatic_wagering"] is False
    assert promotion["protections"]["real_money"] == "BLOCKED"
    assert promotion["protections"]["external_audit_closed"] is False

    assert matrix["p_matrix_status"] == "GENERATED_GOVERNED_MARKET_SCOPED"
    assert matrix["engine_id"] == ENGINE_ID
    assert matrix["source_ready_input_count"] == EXPECTED_READY_INPUTS
    assert matrix["scored_count"] == EXPECTED_GOVERNED_ROWS
    assert matrix["blocked_count"] == EXPECTED_READY_INPUTS - EXPECTED_GOVERNED_ROWS
    assert len({row["fixture_id"] for row in matrix["rows"]}) == EXPECTED_GOVERNED_ROWS

    for row in matrix["rows"]:
        assert row["market"] == "OVER_2_5"
        assert row["p_matrix"] == row["source_frozen_probability_over_2_5"]
        assert 0.0 < row["p_matrix"] < 1.0
        assert row["odds_used_to_generate_probability"] is False
        assert row["target_outcome_used"] is False
        assert row["bet_decision"] is None

    assert matrix["protections"]["p_matrix_equals_immutable_frozen_probability"] is True
    assert matrix["protections"]["parameter_refit"] is False
    assert matrix["protections"]["parameter_search"] is False
    assert matrix["protections"]["bet_decisions_generated"] is False
    assert matrix["protections"]["real_money"] == "BLOCKED"
