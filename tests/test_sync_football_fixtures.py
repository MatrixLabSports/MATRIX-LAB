from unittest.mock import Mock, patch

import pytest

from app.application.football.sync_fixtures import (
    sync_football_fixtures,
)


def test_sync_football_fixtures_fetches_and_upserts_records():
    client = Mock()
    repository = Mock()
    records = [Mock(), Mock()]

    with patch(
        "app.application.football.sync_fixtures.get_fixture_records_by_date",
        return_value=records,
    ) as get_records:
        result = sync_football_fixtures(
            client=client,
            repository=repository,
            date="2026-08-16",
        )

    get_records.assert_called_once_with(
        client,
        "2026-08-16",
    )
    repository.upsert_records.assert_called_once_with(records)
    repository.save_matches.assert_not_called()
    assert result == records


def test_sync_football_fixtures_saves_empty_result():
    client = Mock()
    repository = Mock()

    with patch(
        "app.application.football.sync_fixtures.get_fixture_records_by_date",
        return_value=[],
    ) as get_records:
        result = sync_football_fixtures(
            client=client,
            repository=repository,
            date="2026-08-16",
        )

    get_records.assert_called_once_with(
        client,
        "2026-08-16",
    )
    repository.upsert_records.assert_called_once_with([])
    repository.save_matches.assert_not_called()
    assert result == []


def test_sync_football_fixtures_does_not_save_when_fetch_fails():
    client = Mock()
    repository = Mock()

    with patch(
        "app.application.football.sync_fixtures.get_fixture_records_by_date",
        side_effect=ValueError("fallo del proveedor"),
    ):
        with pytest.raises(
            ValueError,
            match="fallo del proveedor",
        ):
            sync_football_fixtures(
                client=client,
                repository=repository,
                date="2026-08-16",
            )

    repository.upsert_records.assert_not_called()
    repository.save_matches.assert_not_called()
