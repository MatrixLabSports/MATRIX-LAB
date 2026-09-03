from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.providers.sportradar.response_validation import (
    validate_sportradar_collection,
)
from app.providers.sportradar.soccer_adapter import (
    SportradarSoccerCompetition,
    adapt_sportradar_soccer_competition,
)
from app.providers.sportradar.tennis_adapter import (
    SportradarTennisCompetition,
    adapt_sportradar_tennis_competition,
)


_CONTRACT_ID = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class SportradarCatalogIngestion:
    sport: str
    records: tuple[object, ...]
    received_count: int
    accepted_count: int
    rejected_count: int
    payload_fingerprint: str
    generated_at: str


def _validate_catalog_request(
    *,
    sport: str,
    request_contract_id: object,
    path: object,
) -> tuple[str, str]:
    if sport not in {"tennis", "football"}:
        raise ValueError("INVALID_SPORTRADAR_SPORT")
    if (
        not isinstance(request_contract_id, str)
        or not _CONTRACT_ID.fullmatch(request_contract_id)
    ):
        raise ValueError("INVALID_SPORTRADAR_REQUEST_CONTRACT_ID")
    if (
        not isinstance(path, str)
        or "?" in path
        or "#" in path
        or not path.endswith("/competitions.json")
    ):
        raise ValueError("INVALID_SPORTRADAR_CATALOG_PATH")

    expected_prefix = "/tennis/" if sport == "tennis" else "/soccer/"
    if not path.startswith(expected_prefix):
        raise ValueError("SPORTRADAR_CATALOG_SPORT_PATH_MISMATCH")

    return request_contract_id.lower(), path


def ingest_sportradar_competitions(
    *,
    client: Any,
    sport: str,
    request_contract_id: str,
    path: str,
) -> SportradarCatalogIngestion:
    request_contract_id, path = _validate_catalog_request(
        sport=sport,
        request_contract_id=request_contract_id,
        path=path,
    )

    payload = client.get(
        path=path,
        request_contract_id=request_contract_id,
        params=None,
    )
    envelope = validate_sportradar_collection(
        payload,
        collection_name="competitions",
    )

    adapter = (
        adapt_sportradar_tennis_competition
        if sport == "tennis"
        else adapt_sportradar_soccer_competition
    )

    records = []
    rejected = 0
    for item in envelope.items:
        try:
            records.append(adapter(item))
        except ValueError:
            rejected += 1

    return SportradarCatalogIngestion(
        sport=sport,
        records=tuple(records),
        received_count=len(envelope.items),
        accepted_count=len(records),
        rejected_count=rejected,
        payload_fingerprint=envelope.payload_fingerprint,
        generated_at=envelope.generated_at,
    )
