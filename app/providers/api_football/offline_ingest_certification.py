from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date as date_type
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from app.application.football.sync_fixtures import (
    sync_football_fixtures,
)
from app.providers.api_football.response_validation import (
    validate_api_football_response_envelope,
)
from app.sports.football.repository import (
    FootballMatchRepository,
)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha(value: Mapping[str, Any]) -> str:
    return sha256(
        _json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ApiFootballOfflineIngestCertification:
    status: str
    provider_key: str
    mode: str
    date: str
    source_payload_fingerprint: str
    received_count: int
    accepted_count: int
    rejected_count: int
    replay_request_count: int
    reconciliation_call_count: int
    repository_idempotent: bool
    zero_network_calls: bool
    real_provider_execution_authorized: bool
    automatic_provider_switch: bool
    automatic_wagering: bool
    blockers: tuple[str, ...]
    certification_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-offline-ingest-certification/1"
            ),
            "status": self.status,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "date": self.date,
            "source_payload_fingerprint": (
                self.source_payload_fingerprint
            ),
            "received_count": self.received_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "replay_request_count": self.replay_request_count,
            "reconciliation_call_count": (
                self.reconciliation_call_count
            ),
            "repository_idempotent": (
                self.repository_idempotent
            ),
            "zero_network_calls": self.zero_network_calls,
            "real_provider_execution_authorized": (
                self.real_provider_execution_authorized
            ),
            "automatic_provider_switch": (
                self.automatic_provider_switch
            ),
            "automatic_wagering": (
                self.automatic_wagering
            ),
            "blockers": list(self.blockers),
        }


class _OfflineReplayClient:
    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        date: str,
    ) -> None:
        self._payload = deepcopy(dict(payload))
        self._date = date
        self.request_count = 0
        self.network_call_count = 0

    def get(
        self,
        path: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if path != "/fixtures":
            raise ValueError(
                "OFFLINE_REPLAY_ENDPOINT_FORBIDDEN"
            )

        if dict(params) != {"date": self._date}:
            raise ValueError(
                "OFFLINE_REPLAY_PARAMETERS_MISMATCH"
            )

        self.request_count += 1
        return deepcopy(self._payload)


class _TrackingFootballMatchRepository(
    FootballMatchRepository
):
    def __init__(
        self,
        file_path: str | Path,
    ) -> None:
        super().__init__(file_path)
        self.reconciliation_call_count = 0

    def reconcile_records_for_date(
        self,
        *,
        date: str,
        current_records,
    ) -> None:
        self.reconciliation_call_count += 1
        return super().reconcile_records_for_date(
            date=date,
            current_records=current_records,
        )


def _canonical_date(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "OFFLINE_REPLAY_DATE_REQUIRED"
        )

    parsed = date_type.fromisoformat(value)

    if parsed.isoformat() != value:
        raise ValueError(
            "OFFLINE_REPLAY_CANONICAL_DATE_REQUIRED"
        )

    return value


def certify_api_football_offline_fixture_ingest(
    *,
    payload: Mapping[str, Any],
    date: str,
) -> ApiFootballOfflineIngestCertification:
    canonical_date = _canonical_date(date)

    envelope = validate_api_football_response_envelope(
        payload,
        endpoint="/fixtures",
    )

    replay_client = _OfflineReplayClient(
        payload=payload,
        date=canonical_date,
    )

    blockers: list[str] = []

    with TemporaryDirectory(
        prefix="matrix-api-football-replay-"
    ) as temporary_directory:
        repository_path = (
            Path(temporary_directory)
            / "football-fixtures.json"
        )
        repository = _TrackingFootballMatchRepository(
            repository_path
        )

        first_records = sync_football_fixtures(
            replay_client,
            repository,
            canonical_date,
        )

        first_bytes = (
            repository_path.read_bytes()
            if repository_path.exists()
            else b""
        )

        second_records = sync_football_fixtures(
            replay_client,
            repository,
            canonical_date,
        )

        second_bytes = (
            repository_path.read_bytes()
            if repository_path.exists()
            else b""
        )

    received_count = len(envelope.response)
    accepted_count = len(first_records)
    rejected_count = max(
        0,
        received_count - accepted_count,
    )

    first_identities = tuple(
        record.identity
        for record in first_records
    )
    second_identities = tuple(
        record.identity
        for record in second_records
    )

    repository_idempotent = (
        first_bytes == second_bytes
        and first_identities == second_identities
    )

    if rejected_count != 0:
        blockers.append(
            "OFFLINE_REPLAY_RECORD_REJECTIONS_PRESENT"
        )

    if replay_client.request_count != 2:
        blockers.append(
            "OFFLINE_REPLAY_REQUEST_COUNT_INVALID"
        )

    if repository.reconciliation_call_count != 2:
        blockers.append(
            "OFFLINE_REPLAY_RECONCILIATION_REQUIRED"
        )

    if not repository_idempotent:
        blockers.append(
            "OFFLINE_REPLAY_REPOSITORY_NOT_IDEMPOTENT"
        )

    zero_network_calls = (
        replay_client.network_call_count == 0
    )

    if not zero_network_calls:
        blockers.append(
            "OFFLINE_REPLAY_NETWORK_CALL_FORBIDDEN"
        )

    status = (
        "CERTIFIED"
        if not blockers
        else "NOT_CERTIFIED"
    )

    base = {
        "schema": (
            "matrix.api-football-offline-ingest-certification/1"
        ),
        "status": status,
        "provider_key": "api_football",
        "mode": "OFFLINE_REPLAY",
        "date": canonical_date,
        "source_payload_fingerprint": (
            envelope.payload_fingerprint
        ),
        "received_count": received_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "replay_request_count": replay_client.request_count,
        "reconciliation_call_count": (
            repository.reconciliation_call_count
        ),
        "repository_idempotent": repository_idempotent,
        "zero_network_calls": zero_network_calls,
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "blockers": list(blockers),
    }

    return ApiFootballOfflineIngestCertification(
        status=status,
        provider_key="api_football",
        mode="OFFLINE_REPLAY",
        date=canonical_date,
        source_payload_fingerprint=(
            envelope.payload_fingerprint
        ),
        received_count=received_count,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        replay_request_count=replay_client.request_count,
        reconciliation_call_count=(
            repository.reconciliation_call_count
        ),
        repository_idempotent=repository_idempotent,
        zero_network_calls=zero_network_calls,
        real_provider_execution_authorized=False,
        automatic_provider_switch=False,
        automatic_wagering=False,
        blockers=tuple(blockers),
        certification_fingerprint=_sha(base),
    )


def verify_api_football_offline_ingest_certification(
    certification: ApiFootballOfflineIngestCertification,
) -> ApiFootballOfflineIngestCertification:
    if not isinstance(
        certification,
        ApiFootballOfflineIngestCertification,
    ):
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_TYPE_REQUIRED"
        )

    if (
        _sha(certification.payload())
        != certification.certification_fingerprint
    ):
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_INTEGRITY_FAILURE"
        )

    if (
        certification.provider_key != "api_football"
        or certification.mode != "OFFLINE_REPLAY"
    ):
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_SCOPE_INVALID"
        )

    if (
        certification.real_provider_execution_authorized
        is not False
        or certification.automatic_provider_switch
        is not False
        or certification.automatic_wagering
        is not False
        or certification.zero_network_calls
        is not True
    ):
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_SAFETY_FAILURE"
        )

    expected_status = (
        "CERTIFIED"
        if (
            not certification.blockers
            and certification.rejected_count == 0
            and certification.replay_request_count == 2
            and certification.reconciliation_call_count == 2
            and certification.repository_idempotent
        )
        else "NOT_CERTIFIED"
    )

    if certification.status != expected_status:
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_STATUS_INVALID"
        )

    return certification


def require_api_football_offline_ingest_certified(
    certification: ApiFootballOfflineIngestCertification,
) -> None:
    verified = (
        verify_api_football_offline_ingest_certification(
            certification
        )
    )

    if verified.status != "CERTIFIED":
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_REQUIRED"
        )
