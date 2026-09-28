from pathlib import Path

from tools.api_football_engine_registry_adjudication import adjudicate


def test_physical_engine_adjudication_fails_closed_without_governed_engine():
    result = adjudicate(Path("."))

    assert result["canonical_ready_input_count"] > 0
    assert result["core_registry_football_status"] == "NOT_REGISTERED"
    assert result["engine_executable_count"] == 0
    assert result["governed_p_matrix_engine_available"] is False
    assert result["governed_p_matrix_engine"] is None
    assert result["p_matrix_status"] == "NOT_GENERATED"
    assert result["decision"] == "NO_GOVERNED_ENGINE_EXECUTABLE"
    assert result["protections"]["no_silent_promotion"] is True
    assert result["protections"]["odds_to_p_matrix"] is False
    assert result["protections"]["automatic_wagering"] is False
    assert result["protections"]["real_money"] == "BLOCKED"


def test_poisson_is_physically_executable_but_research_only():
    result = adjudicate(Path("."))
    poisson = next(
        row for row in result["classifications"]
        if row["engine_id"] == "transparent_poisson_baseline_v1"
    )

    assert poisson["classification"] == "EXPERIMENTAL_ONLY"
    assert poisson["technical_execution_verified"] is True
    assert poisson["engine_executable_for_p_matrix"] is False
    assert poisson["sample_market_count"] >= 3
    assert poisson["decision"] == "NO_BET"
    assert poisson["model_status"] == "EXPERIMENTAL_NOT_PROMOTED"


def test_legacy_engine_identifiers_cannot_be_treated_as_executable_without_adjudication():
    result = adjudicate(Path("."))
    legacy = {
        row["engine_id"]: row
        for row in result["classifications"]
        if row["engine_id"] != "transparent_poisson_baseline_v1"
    }
    assert set(legacy) == {"R315", "R442", "R316", "R318", "R320", "R322"}
    assert all(row["classification"] == "NOT_PHYSICALLY_ADJUDICATED" for row in legacy.values())
    assert all(row["engine_executable"] is False for row in legacy.values())
