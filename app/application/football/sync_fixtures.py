from typing import Any

from app.providers.api_football.fixture_service import (
    get_fixture_records_by_date,
)


def sync_football_fixtures(
    client: Any,
    repository: Any,
    date: str,
):
    records = get_fixture_records_by_date(
        client,
        date,
    )

    repository.reconcile_records_for_date(
        date=date,
        current_records=records,
    )

    return records
