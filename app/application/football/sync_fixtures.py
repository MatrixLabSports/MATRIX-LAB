from typing import Any

from app.application.football.sync_result import FootballSyncResult
from app.providers.api_football.fixture_service import (
    get_fixture_ingestion_by_date,
)


def sync_football_fixtures(
    client: Any,
    repository: Any,
    date: str,
):
    ingestion = get_fixture_ingestion_by_date(
        client,
        date,
    )

    status = (
        "completed"
        if ingestion.rejected_count == 0
        else "partial"
    )

    sync_result = FootballSyncResult(
        status=status,
        received_count=ingestion.received_count,
        accepted_count=ingestion.accepted_count,
        rejected_count=ingestion.rejected_count,
    )

    if sync_result.can_reconcile_missing:
        repository.reconcile_records_for_date(
            date=date,
            current_records=ingestion.records,
        )
    else:
        repository.upsert_records(
            ingestion.records
        )

    return ingestion.records
