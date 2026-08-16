from typing import Any

from app.providers.api_football.fixture_service import (
    get_fixtures_by_date,
)


def sync_football_fixtures(
    client: Any,
    repository: Any,
    date: str,
):
    matches = get_fixtures_by_date(
        client,
        date,
    )

    repository.save_matches(matches)

    return matches