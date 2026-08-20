from datetime import datetime, timezone

import pytest

from app.application.football.historical_coverage import (
    build_football_coverage_ledger,
)
from app.application.tennis.historical_coverage import (
    build_tennis_coverage_ledger,
)
from app.core.admission_fingerprint import AdmissionEvidence
from app.core.dataset_manifest import DatasetRowEvidence
from app.core.historical_coverage import HistoricalCoverageObservation


UTC = timezone.utc
CUTOFF = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
KNOWN_AT = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)


def admission(
    sport: str,
    entity_key: str,
    *,
    status: str = "ADMIT",
    model_eligible: bool = True,
    reasons=(),
    source_status: str = "PASS",
):
    return AdmissionEvidence(
        sport=sport,
        entity_key=entity_key,
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status=source_status,
        admission_status=status,
        model_eligible=model_eligible,
        reason_codes=tuple(reasons),
        source_fingerprint=("a" if sport == "football" else "b") * 64,
    )


def observation(
    sport: str,
    subject_key: str,
    index: int,
    *,
    admitted: bool = True,
    deep_ready: bool = True,
    present: int = 8,
    total: int = 10,
    blocker: str = "QUALITY_BLOCK",
):
    event_key = f"{sport}:EVENT:{index}"

    if admitted:
        evidence = admission(
            sport,
            event_key,
        )
    else:
        evidence = admission(
            sport,
            event_key,
            status="BLOCK",
            model_eligible=False,
            reasons=(blocker,),
            source_status="BLOCK",
        )

    row = DatasetRowEvidence(
        sport=sport,
        canonical_entity_key=event_key,
        admission_evidence=evidence,
        row_payload={"index": index},
    )

    return HistoricalCoverageObservation(
        sport=sport,
        subject_key=subject_key,
        event_key=event_key,
        row_evidence=row,
        deep_ready=deep_ready,
        core_stats_present=present,
        core_stats_total=total,
    )


def test_tennis_5_ready_10_watch_20_block():
    rows = [
        observation("tennis", "PLAYER:1", index)
        for index in range(7)
    ]

    ledger = build_tennis_coverage_ledger(
        player_key="PLAYER:1",
        observations=rows,
    )

    assert ledger["window_status"]["5"]["status"] == "READY"
    assert ledger["window_status"]["10"]["status"] == "WATCH"
    assert ledger["window_status"]["20"]["status"] == "BLOCK"


def test_football_50_window_is_ready_with_sufficient_history():
    rows = [
        observation("football", "TEAM:1", index)
        for index in range(55)
    ]

    ledger = build_football_coverage_ledger(
        team_key="TEAM:1",
        observations=rows,
    )

    assert ledger["window_status"]["50"]["status"] == "READY"
    assert ledger["window_status"]["50"]["missing_slots"] == 0


def test_blocked_admission_evidence_does_not_count_as_eligible():
    rows = [
        observation("tennis", "PLAYER:1", index)
        for index in range(5)
    ]
    rows += [
        observation(
            "tennis",
            "PLAYER:1",
            100 + index,
            admitted=False,
            blocker="CHRONOLOGY_BLOCK",
        )
        for index in range(5)
    ]

    ledger = build_tennis_coverage_ledger(
        player_key="PLAYER:1",
        observations=rows,
    )

    assert ledger["eligible_observations"] == 5
    assert ledger["blocked_observations"] == 5
    assert ledger["blocker_counts"]["CHRONOLOGY_BLOCK"] == 5


def test_missing_core_coverage_is_not_imputed_to_zero():
    rows = [
        observation(
            "football",
            "TEAM:1",
            1,
            present=0,
            total=0,
            deep_ready=False,
        )
    ]

    ledger = build_football_coverage_ledger(
        team_key="TEAM:1",
        observations=rows,
    )

    assert ledger["average_core_stat_coverage"] is None


def test_deep_ready_is_reported_separately():
    rows = [
        observation(
            "tennis",
            "PLAYER:1",
            index,
            deep_ready=index < 3,
        )
        for index in range(5)
    ]

    ledger = build_tennis_coverage_ledger(
        player_key="PLAYER:1",
        observations=rows,
    )

    assert ledger["eligible_observations"] == 5
    assert ledger["deep_ready_observations"] == 3


def test_cross_sport_subject_collision_is_blocked():
    rows = [
        observation("football", "SHARED:1", 1),
        observation("tennis", "SHARED:1", 2),
    ]

    with pytest.raises(
        ValueError,
        match="CROSS_SPORT_SUBJECT_COLLISION",
    ):
        build_football_coverage_ledger(
            team_key="SHARED:1",
            observations=rows,
        )


def test_duplicate_event_key_is_blocked():
    row = observation("tennis", "PLAYER:1", 1)

    with pytest.raises(
        ValueError,
        match="DUPLICATE_EVENT_KEY",
    ):
        build_tennis_coverage_ledger(
            player_key="PLAYER:1",
            observations=[row, row],
        )


def test_p51_row_sport_must_match_coverage_sport():
    football_event = "football:EVENT:1"
    football_admission = admission(
        "football",
        football_event,
    )
    football_row = DatasetRowEvidence(
        sport="football",
        canonical_entity_key=football_event,
        admission_evidence=football_admission,
        row_payload={"index": 1},
    )

    with pytest.raises(
        ValueError,
        match="CROSS_SPORT_ROW_EVIDENCE",
    ):
        HistoricalCoverageObservation(
            sport="tennis",
            subject_key="PLAYER:1",
            event_key="tennis:EVENT:1",
            row_evidence=football_row,
            deep_ready=True,
            core_stats_present=8,
            core_stats_total=10,
        )


def test_safety_flags_remain_false():
    ledger = build_tennis_coverage_ledger(
        player_key="PLAYER:1",
        observations=[
            observation("tennis", "PLAYER:1", 1)
        ],
    )

    assert ledger["automatic_model_promotion"] is False
    assert ledger["automatic_provider_switch"] is False
    assert ledger["automatic_wagering"] is False
