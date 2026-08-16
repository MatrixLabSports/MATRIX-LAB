import pytest

from app.sports.football.sync_state import FootballSyncState


def test_football_sync_state_can_be_created():
    state = FootballSyncState(
        status="seen_current_sync",
    )

    assert state.status == "seen_current_sync"


def test_football_sync_state_rejects_unknown_status():
    with pytest.raises(
        ValueError,
        match="estado de sincronización de fútbol no permitido",
    ):
        FootballSyncState(
            status="unknown",
        )


def test_football_sync_state_accepts_temporarily_missing():
    state = FootballSyncState(
        status="temporarily_missing",
    )

    assert state.status == "temporarily_missing"


def test_football_sync_state_accepts_confirmed_removed():
    state = FootballSyncState(
        status="confirmed_removed",
    )

    assert state.status == "confirmed_removed"