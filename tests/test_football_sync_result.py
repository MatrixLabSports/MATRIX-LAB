import pytest

from app.application.football.sync_result import FootballSyncResult


def test_football_sync_result_can_be_completed():
    result = FootballSyncResult(
        status="completed",
        received_count=736,
        accepted_count=736,
        rejected_count=0,
    )

    assert result.status == "completed"
    assert result.received_count == 736
    assert result.accepted_count == 736
    assert result.rejected_count == 0
    assert result.can_reconcile_missing is True


def test_football_sync_result_partial_cannot_reconcile_missing():
    result = FootballSyncResult(
        status="partial",
        received_count=736,
        accepted_count=700,
        rejected_count=36,
    )

    assert result.can_reconcile_missing is False


def test_football_sync_result_failed_cannot_reconcile_missing():
    result = FootballSyncResult(
        status="failed",
        received_count=0,
        accepted_count=0,
        rejected_count=0,
    )

    assert result.can_reconcile_missing is False


def test_football_sync_result_rejects_unknown_status():
    with pytest.raises(
        ValueError,
        match="estado de sincronización de fútbol no permitido",
    ):
        FootballSyncResult(
            status="unknown",
            received_count=0,
            accepted_count=0,
            rejected_count=0,
        )


def test_football_sync_result_rejects_negative_counts():
    with pytest.raises(
        ValueError,
        match="conteos de sincronización deben ser enteros no negativos",
    ):
        FootballSyncResult(
            status="completed",
            received_count=-1,
            accepted_count=0,
            rejected_count=0,
        )


def test_football_sync_result_rejects_processed_count_above_received():
    with pytest.raises(
        ValueError,
        match="aceptados y rechazados no pueden superar los recibidos",
    ):
        FootballSyncResult(
            status="partial",
            received_count=100,
            accepted_count=90,
            rejected_count=20,
        )


def test_completed_sync_requires_all_received_records_accounted_for():
    with pytest.raises(
        ValueError,
        match="sincronización completa debe contabilizar todos los recibidos",
    ):
        FootballSyncResult(
            status="completed",
            received_count=100,
            accepted_count=90,
            rejected_count=0,
        )
