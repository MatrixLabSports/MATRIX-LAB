import pytest
from tools.matrix_tennis_calendar_evidence_gate import evaluate


def sample():
    return {
        "schema": "MATRIX_OPERA_TENNIS_CALENDAR_CROSSCHECK_V1",
        "sources": [{"provider": "SofaScore"}, {"provider": "Flashscore"}],
        "observed_name_matches": ["match" + str(i) for i in range(5)],
        "sofascore_observed_matches": [{"id": str(i)} for i in range(5)],
        "flashscore_observed_match_ids": [{"mid": str(i)} for i in range(5)],
    }


def test_observed_ids_do_not_authorize_signals():
    result = evaluate(sample())
    assert result["observed_count"] == 5
    assert result["cross_provider_observations_present"]
    assert not result["utc_kickoff_certified"]
    assert not result["canonical_fixture_export_authorized"]
    assert not result["telegram_signals_authorized"]
    assert result["real_money"] == "BLOCKED"


def test_forged_flags_do_not_escalate_trust():
    item = sample()
    item.update({"timezone_of_display_times_verified": True,
                 "surface_verified": True, "physical_capture_verified": True,
                 "telegram_signals_authorized": True})
    result = evaluate(item)
    assert result["status"] == "OBSERVED_ONLY_NOT_CERTIFIED"
    assert not result["probability_generation_authorized"]


def test_duplicate_provider_ids_fail_observation_count():
    item = sample()
    item["flashscore_observed_match_ids"][1]["mid"] = "0"
    assert evaluate(item)["observed_count"] == 0


def test_invalid_schema_fails_closed():
    with pytest.raises(ValueError, match="UNTRUSTED"):
        evaluate({"schema": "other"})
