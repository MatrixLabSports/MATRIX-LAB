from datetime import datetime, timezone

from app.application.tennis.point_in_time_admission import evaluate_tennis_admission


def test_tennis_blocks_knowledge_after_cutoff():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:1",
        cutoff=cutoff,
        known_at=datetime(
            2026,
            8,
            20,
            12,
            0,
            1,
            tzinfo=timezone.utc,
        ),
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "KNOWN_AFTER_CUTOFF" in decision.reason_codes

def test_tennis_blocks_unfinished_match():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:2",
        cutoff=cutoff,
        known_at=datetime(
            2026,
            8,
            20,
            11,
            0,
            tzinfo=timezone.utc,
        ),
        source_status="PASS",
        match_finished=False,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "MATCH_NOT_FINISHED" in decision.reason_codes

def test_tennis_watch_source_is_not_model_eligible():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:3",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="WATCH",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "WATCH"
    assert decision.model_eligible is False
    assert "SOURCE_WATCH_EXCLUDED" in decision.reason_codes


def test_tennis_block_source_is_blocked():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:4",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="BLOCK",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "SOURCE_BLOCK" in decision.reason_codes

def test_tennis_blocks_unverified_intra_tournament_chronology():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:5",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=False,
        same_tournament_cutoff_sensitive=True,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "INTRA_TOURNAMENT_CHRONOLOGY_UNVERIFIED" in decision.reason_codes

def test_tennis_blocks_missing_canonical_match_key():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="   ",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "MISSING_CANONICAL_MATCH_KEY" in decision.reason_codes

def test_tennis_blocks_unknown_source_status():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:6",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="UNKNOWN",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "INVALID_SOURCE_STATUS" in decision.reason_codes

def test_tennis_blocks_naive_temporal_context():
    cutoff = datetime(2026, 8, 20, 12, 0)

    decision = evaluate_tennis_admission(
        match_key="T:7",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0),
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "BLOCK"
    assert decision.model_eligible is False
    assert "TIMEZONE_UNVERIFIED" in decision.reason_codes

def test_tennis_admits_fully_valid_historical_record():
    cutoff = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    decision = evaluate_tennis_admission(
        match_key="T:8",
        cutoff=cutoff,
        known_at=datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc),
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )

    assert decision.admission_status == "ADMIT"
    assert decision.model_eligible is True
    assert decision.reason_codes == ()
