from datetime import datetime, timezone

import pytest

from app.application.football.point_in_time_admission import (
    evaluate_football_admission,
)


UTC = timezone.utc
CUTOFF = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def valid_decision(**overrides):
    values = {
        "fixture_key": "F:VALID",
        "kickoff": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        "cutoff": CUTOFF,
        "known_at": datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
        "source_status": "PASS",
        "match_finished": True,
    }
    values.update(overrides)
    return evaluate_football_admission(**values)


def test_football_blocks_kickoff_not_before_cutoff():
    decision = valid_decision(kickoff=CUTOFF)

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "KICKOFF_NOT_BEFORE_CUTOFF" in decision.reason_codes


def test_football_blocks_knowledge_after_cutoff():
    decision = valid_decision(
        known_at=datetime(2026, 8, 20, 12, 0, 1, tzinfo=UTC)
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "KNOWN_AFTER_CUTOFF" in decision.reason_codes


def test_football_blocks_unfinished_match():
    decision = valid_decision(match_finished=False)

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "MATCH_NOT_FINISHED" in decision.reason_codes


def test_football_watch_source_is_not_model_eligible():
    decision = valid_decision(source_status="WATCH")

    assert decision.admission_status == "WATCH"
    assert decision.model_eligible is False
    assert "SOURCE_WATCH_EXCLUDED" in decision.reason_codes


def test_football_block_source_is_blocked():
    decision = valid_decision(source_status="BLOCK")

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "SOURCE_BLOCK" in decision.reason_codes


def test_football_blocks_missing_canonical_fixture_key():
    decision = valid_decision(fixture_key="   ")

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "MISSING_CANONICAL_FIXTURE_KEY" in decision.reason_codes


def test_football_blocks_unknown_source_status():
    decision = valid_decision(source_status="UNKNOWN")

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "INVALID_SOURCE_STATUS" in decision.reason_codes


@pytest.mark.parametrize("field", ["kickoff", "cutoff", "known_at"])
def test_football_blocks_naive_temporal_context(field):
    values = {
        "fixture_key": "F:TIME",
        "kickoff": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        "cutoff": CUTOFF,
        "known_at": datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
        "source_status": "PASS",
        "match_finished": True,
    }
    values[field] = values[field].replace(tzinfo=None)

    decision = evaluate_football_admission(**values)

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "TIMEZONE_UNVERIFIED" in decision.reason_codes


def test_football_admits_fully_valid_historical_record():
    decision = valid_decision()

    assert decision.admission_status == "ADMIT"
    assert decision.model_eligible is True
    assert decision.reason_codes == ()
