from unittest.mock import Mock, patch

import pytest

from app.application.football.sync_fixtures import sync_football_fixtures
from app.providers.api_football.fixture_service import FixtureIngestionResult


def _ingestion(records, *, received=None, rejected=0):
    accepted = len(records)
    if received is None:
        received = accepted + rejected
    return FixtureIngestionResult(
        records=records,
        received_count=received,
        accepted_count=accepted,
        rejected_count=rejected,
    )


def test_sync_football_fixtures_fetches_and_reconciles_records_by_date():
    client = Mock()
    repository = Mock()
    records = [Mock(), Mock()]
    ingestion = _ingestion(records)

    with patch(
        "app.application.football.sync_fixtures.get_fixture_ingestion_by_date",
        return_value=ingestion,
    ) as get_ingestion:
        result = sync_football_fixtures(
            client=client,
            repository=repository,
            date="2026-08-16",
        )

    get_ingestion.assert_called_once_with(client, "2026-08-16")
    repository.reconcile_records_for_date.assert_called_once_with(
        date="2026-08-16",
        current_records=records,
    )
    repository.upsert_records.assert_not_called()
    repository.save_matches.assert_not_called()
    assert result == records


def test_sync_football_fixtures_reconciles_empty_result_by_date():
    client = Mock()
    repository = Mock()
    ingestion = _ingestion([])

    with patch(
        "app.application.football.sync_fixtures.get_fixture_ingestion_by_date",
        return_value=ingestion,
    ) as get_ingestion:
        result = sync_football_fixtures(
            client=client,
            repository=repository,
            date="2026-08-16",
        )

    get_ingestion.assert_called_once_with(client, "2026-08-16")
    repository.reconcile_records_for_date.assert_called_once_with(
        date="2026-08-16",
        current_records=[],
    )
    repository.upsert_records.assert_not_called()
    repository.save_matches.assert_not_called()
    assert result == []


def test_sync_football_fixtures_does_not_save_when_fetch_fails():
    client = Mock()
    repository = Mock()

    with patch(
        "app.application.football.sync_fixtures.get_fixture_ingestion_by_date",
        side_effect=ValueError("fallo del proveedor"),
    ):
        with pytest.raises(ValueError, match="fallo del proveedor"):
            sync_football_fixtures(
                client=client,
                repository=repository,
                date="2026-08-16",
            )

    repository.reconcile_records_for_date.assert_not_called()
    repository.upsert_records.assert_not_called()
    repository.save_matches.assert_not_called()


def test_sync_football_fixtures_does_not_reconcile_missing_on_partial_ingestion():
    client = Mock()
    repository = Mock()
    records = [Mock()]
    partial_ingestion = _ingestion(records, received=2, rejected=1)

    with patch(
        "app.application.football.sync_fixtures.get_fixture_ingestion_by_date",
        return_value=partial_ingestion,
    ):
        result = sync_football_fixtures(
            client=client,
            repository=repository,
            date="2026-08-16",
        )

    repository.reconcile_records_for_date.assert_not_called()
    repository.upsert_records.assert_called_once_with(records)
    assert result == records
