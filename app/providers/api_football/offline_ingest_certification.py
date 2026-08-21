from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import textwrap
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from app.application.football.sync_fixtures import sync_football_fixtures
from app.core.provider_shadow_rehearsal_evidence import (
    SQLiteProviderShadowRehearsalEvidenceStore,
    build_provider_shadow_attestation_key_reference,
    verify_provider_shadow_rehearsal_attestation,
)
from app.core.provider_request_contract import (
    request_parameter_values_fingerprint,
)
from app.core.secret_reference import resolve_secret_runtime
from app.providers.api_football.fixture_adapter import (
    adapt_api_football_fixture,
    adapt_api_football_identity,
)
from app.providers.api_football.fixture_service import (
    get_fixture_ingestion_by_date,
)
from app.providers.api_football.response_validation import (
    validate_api_football_response_envelope,
)
from app.sports.football.repository import FootballMatchRepository


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha(value: Mapping[str, Any]) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _aware_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("OFFLINE_INGEST_AWARE_DATETIME_REQUIRED")
    return value.astimezone(timezone.utc).isoformat()


def _canonical_date(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("OFFLINE_REPLAY_DATE_REQUIRED")
    parsed = date_type.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("OFFLINE_REPLAY_CANONICAL_DATE_REQUIRED")
    return value


def _source_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip().lower()
    if (
        len(revision) < 7
        or len(revision) > 64
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise ValueError("OFFLINE_INGEST_SOURCE_REVISION_INVALID")
    return revision



AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV = (
    "MATRIX_API_FOOTBALL_OFFLINE_INGEST_EVIDENCE_DB"
)


def _offline_ingest_store_identity(
    path: str | Path,
) -> str:
    resolved = Path(path).expanduser().resolve()

    return _sha(
        {
            "schema": (
                "matrix.api-football-offline-ingest-store/2"
            ),
            "path": str(
                resolved
            ),
            "provider_key": "api_football",
            "purpose": (
                "OFFLINE_FIXTURE_INGEST_CERTIFICATION"
            ),
        }
    )


def _authoritative_offline_ingest_store_path() -> Path:
    raw = os.environ.get(
        AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV
    )

    if (
        not isinstance(raw, str)
        or not raw.strip()
    ):
        raise ValueError(
            "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_REQUIRED"
        )

    path = Path(
        raw.strip()
    ).expanduser()

    if not path.is_absolute():
        raise ValueError(
            "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ABSOLUTE_REQUIRED"
        )

    return path.resolve()


def build_authoritative_api_football_offline_ingest_evidence_store():
    return SQLiteApiFootballOfflineIngestEvidenceStore(
        _authoritative_offline_ingest_store_path()
    )

class _OfflineReplayClient:
    def __init__(self, *, payload: Mapping[str, Any], date: str) -> None:
        self._payload = deepcopy(dict(payload))
        self._date = date
        self.request_count = 0

    def get(self, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if path != "/fixtures":
            raise ValueError("OFFLINE_REPLAY_ENDPOINT_FORBIDDEN")
        if dict(params) != {"date": self._date}:
            raise ValueError("OFFLINE_REPLAY_PARAMETERS_MISMATCH")
        self.request_count += 1
        return deepcopy(self._payload)


class _TrackingFootballMatchRepository(FootballMatchRepository):
    def __init__(self, file_path: str | Path) -> None:
        super().__init__(file_path)
        self.reconciliation_call_count = 0

    def reconcile_records_for_date(self, *, date: str, current_records) -> None:
        self.reconciliation_call_count += 1
        return super().reconcile_records_for_date(
            date=date,
            current_records=current_records,
        )


def _offline_topology_fingerprint() -> str:
    sources = {
        "offline_client": inspect.getsource(_OfflineReplayClient),
        "sync": inspect.getsource(sync_football_fixtures),
        "fixture_ingestion": inspect.getsource(get_fixture_ingestion_by_date),
        "fixture_adapter": inspect.getsource(adapt_api_football_fixture),
        "identity_adapter": inspect.getsource(adapt_api_football_identity),
        "repository": inspect.getsource(FootballMatchRepository),
    }

    forbidden_roots = {
        "socket",
        "requests",
        "urllib",
        "http",
        "httpx",
        "aiohttp",
    }
    forbidden_dynamic_calls = {"__import__", "eval", "exec"}

    for name, source in sources.items():
        tree = ast.parse(textwrap.dedent(source), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_roots:
                        raise ValueError("OFFLINE_REPLAY_NETWORK_TOPOLOGY_FORBIDDEN")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in forbidden_roots:
                    raise ValueError("OFFLINE_REPLAY_NETWORK_TOPOLOGY_FORBIDDEN")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in forbidden_dynamic_calls
            ):
                raise ValueError("OFFLINE_REPLAY_DYNAMIC_EXECUTION_FORBIDDEN")

    return _sha(
        {
            "schema": "matrix.api-football-offline-topology/1",
            "sources": sources,
        }
    )


def _verified_shadow_request_provenance(
    evidence_store: SQLiteProviderShadowRehearsalEvidenceStore,
    evidence_id: str,
    *,
    canonical_date: str,
) -> Mapping[str, Any]:
    if (
        type(evidence_store)
        is not SQLiteProviderShadowRehearsalEvidenceStore
    ):
        raise ValueError(
            "AUTHORITATIVE_SHADOW_EVIDENCE_STORE_REQUIRED"
        )

    if (
        not isinstance(evidence_id, str)
        or not evidence_id.strip()
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_REQUEST_EVIDENCE_ID_REQUIRED"
        )

    evidence = evidence_store.get_verified(
        evidence_id
    )

    if evidence is None:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_REQUEST_EVIDENCE_NOT_FOUND"
        )

    if (
        evidence.store_identity
        != evidence_store.store_identity
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_STORE_BINDING_MISMATCH"
        )

    try:
        attestation_valid = (
            verify_provider_shadow_rehearsal_attestation(
                evidence
            )
        )
    except Exception as error:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_ATTESTATION_INVALID"
        ) from error

    if attestation_valid is not True:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_ATTESTATION_INVALID"
        )

    if (
        evidence.provider_key
        != "api_football"
        or evidence.evidence_type
        != "REQUEST"
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_REQUEST_EVIDENCE_REQUIRED"
        )

    parent_id = (
        evidence.parent_readiness_evidence_id
    )

    if (
        not isinstance(parent_id, str)
        or not parent_id
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PARENT_READINESS_REQUIRED"
        )

    parent = evidence_store.get_verified(
        parent_id
    )

    if (
        parent is None
        or parent.provider_key
        != "api_football"
        or parent.evidence_type
        != "READINESS"
        or parent.store_identity
        != evidence_store.store_identity
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PARENT_READINESS_INVALID"
        )

    try:
        parent_attestation_valid = (
            verify_provider_shadow_rehearsal_attestation(
                parent
            )
        )
    except Exception as error:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PARENT_ATTESTATION_INVALID"
        ) from error

    if parent_attestation_valid is not True:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PARENT_ATTESTATION_INVALID"
        )

    if (
        parent.authority_id
        != evidence.authority_id
        or parent.store_identity
        != evidence.store_identity
        or (
            parent.attestation_key_reference_fingerprint
            != evidence.attestation_key_reference_fingerprint
        )
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_AUTHORITY_CHAIN_MISMATCH"
        )

    payload = evidence.payload

    if not isinstance(
        payload,
        Mapping,
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PAYLOAD_REQUIRED"
        )

    required = {
        "contract_id",
        "endpoint_manifest_id",
        "authorization_fingerprint",
        "path",
        "parameter_names",
        "parameter_values_fingerprint",
        "governed_request_client_used",
        "governed_transport_topology_verified",
        "network_call_performed",
        "network_permit_issued",
        "secret_resolved",
        "real_provider_execution_authorized",
    }

    missing = sorted(
        required
        - set(
            payload.keys()
        )
    )

    if missing:
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PROVENANCE_INCOMPLETE"
        )

    if payload["path"] != "/fixtures":
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PATH_MISMATCH"
        )

    if (
        payload["governed_request_client_used"]
        is not True
        or payload[
            "governed_transport_topology_verified"
        ]
        is not True
        or payload["network_call_performed"]
        is not False
        or payload["network_permit_issued"]
        is not False
        or payload["secret_resolved"]
        is not False
        or payload[
            "real_provider_execution_authorized"
        ]
        is not False
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_SAFETY_PROVENANCE_INVALID"
        )

    parameter_names = tuple(
        sorted(
            str(value)
            for value in payload[
                "parameter_names"
            ]
        )
    )

    if parameter_names != (
        "date",
    ):
        raise ValueError(
            "OFFLINE_INGEST_DATE_CONTRACT_BINDING_REQUIRED"
        )

    expected_parameter_values_fingerprint = (
        request_parameter_values_fingerprint(
            {
                "date": canonical_date,
            }
        )
    )

    if (
        str(
            payload[
                "parameter_values_fingerprint"
            ]
        )
        != expected_parameter_values_fingerprint
    ):
        raise ValueError(
            "OFFLINE_INGEST_SHADOW_PARAMETER_VALUES_FINGERPRINT_MISMATCH"
        )

    return {
        "shadow_request_evidence_id": (
            evidence.evidence_id
        ),
        "parent_readiness_evidence_id": (
            parent.evidence_id
        ),
        "request_contract_id": str(
            payload["contract_id"]
        ),
        "endpoint_manifest_id": str(
            payload["endpoint_manifest_id"]
        ),
        "authorization_fingerprint": str(
            payload[
                "authorization_fingerprint"
            ]
        ),
        "request_path": str(
            payload["path"]
        ),
        "parameter_names": (
            parameter_names
        ),
        "parameter_values_fingerprint": (
            expected_parameter_values_fingerprint
        ),
    }


@dataclass(frozen=True)
class ApiFootballOfflineIngestCertification:
    evidence_id: str
    status: str
    provider_key: str
    mode: str
    date: str
    source_payload_fingerprint: str
    shadow_request_evidence_id: str
    parent_readiness_evidence_id: str | None
    request_contract_id: str
    endpoint_manifest_id: str
    authorization_fingerprint: str
    request_path: str
    parameter_names: tuple[str, ...]
    parameter_values_fingerprint: str
    code_fingerprint: str
    source_revision: str
    received_count: int
    accepted_count: int
    rejected_count: int
    replay_request_count: int
    reconciliation_call_count: int
    repository_idempotent: bool
    zero_network_topology_verified: bool
    zero_network_calls: bool
    real_provider_execution_authorized: bool
    automatic_provider_switch: bool
    automatic_wagering: bool
    blockers: tuple[str, ...]
    created_at: str
    store_identity: str
    attestation_key_reference_fingerprint: str
    certification_fingerprint: str
    issuer_attestation: str

    def core_payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.api-football-offline-ingest-certification/3",
            "status": self.status,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "date": self.date,
            "source_payload_fingerprint": self.source_payload_fingerprint,
            "shadow_request_evidence_id": self.shadow_request_evidence_id,
            "parent_readiness_evidence_id": self.parent_readiness_evidence_id,
            "request_contract_id": self.request_contract_id,
            "endpoint_manifest_id": self.endpoint_manifest_id,
            "authorization_fingerprint": self.authorization_fingerprint,
            "request_path": self.request_path,
            "parameter_names": list(self.parameter_names),
            "parameter_values_fingerprint": self.parameter_values_fingerprint,
            "code_fingerprint": self.code_fingerprint,
            "source_revision": self.source_revision,
            "received_count": self.received_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "replay_request_count": self.replay_request_count,
            "reconciliation_call_count": self.reconciliation_call_count,
            "repository_idempotent": self.repository_idempotent,
            "zero_network_topology_verified": self.zero_network_topology_verified,
            "zero_network_calls": self.zero_network_calls,
            "real_provider_execution_authorized": self.real_provider_execution_authorized,
            "automatic_provider_switch": self.automatic_provider_switch,
            "automatic_wagering": self.automatic_wagering,
            "blockers": list(self.blockers),
            "created_at": self.created_at,
            "store_identity": self.store_identity,
            "attestation_key_reference_fingerprint": (
                self.attestation_key_reference_fingerprint
            ),
        }

    def payload(self) -> Mapping[str, Any]:
        return {
            **self.core_payload(),
            "certification_fingerprint": self.certification_fingerprint,
            "issuer_attestation": self.issuer_attestation,
            "evidence_id": self.evidence_id,
        }


def _certification_attestation(
    core_payload: Mapping[str, Any],
    certification_fingerprint: str,
) -> tuple[str, str]:
    reference = build_provider_shadow_attestation_key_reference()
    secret = resolve_secret_runtime(reference)
    signed_payload = {
        "schema": "matrix.api-football-offline-ingest-attestation/1",
        "core_payload": core_payload,
        "certification_fingerprint": certification_fingerprint,
    }
    attestation = hmac.new(
        secret.encode("utf-8"),
        _json(signed_payload).encode("utf-8"),
        sha256,
    ).hexdigest()
    return reference.reference_fingerprint, attestation


def verify_api_football_offline_ingest_certification(
    certification: ApiFootballOfflineIngestCertification,
) -> ApiFootballOfflineIngestCertification:
    if not isinstance(certification, ApiFootballOfflineIngestCertification):
        raise ValueError("OFFLINE_INGEST_CERTIFICATION_TYPE_REQUIRED")

    core = certification.core_payload()
    expected_fingerprint = _sha(
        {
            "schema": "matrix.api-football-offline-ingest-certification-fingerprint/3",
            "core_payload": core,
        }
    )
    if expected_fingerprint != certification.certification_fingerprint:
        raise ValueError("OFFLINE_INGEST_CERTIFICATION_INTEGRITY_FAILURE")

    reference = build_provider_shadow_attestation_key_reference()
    if (
        certification.attestation_key_reference_fingerprint
        != reference.reference_fingerprint
    ):
        raise ValueError("OFFLINE_INGEST_ATTESTATION_REFERENCE_MISMATCH")

    secret = resolve_secret_runtime(reference)
    expected_attestation = hmac.new(
        secret.encode("utf-8"),
        _json(
            {
                "schema": "matrix.api-football-offline-ingest-attestation/1",
                "core_payload": core,
                "certification_fingerprint": certification.certification_fingerprint,
            }
        ).encode("utf-8"),
        sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_attestation,
        certification.issuer_attestation,
    ):
        raise ValueError("OFFLINE_INGEST_ATTESTATION_INVALID")

    expected_evidence_id = _sha(
        {
            "schema": "matrix.api-football-offline-ingest-evidence-id/3",
            "certification_fingerprint": certification.certification_fingerprint,
            "issuer_attestation": certification.issuer_attestation,
        }
    )
    if expected_evidence_id != certification.evidence_id:
        raise ValueError("OFFLINE_INGEST_EVIDENCE_ID_INVALID")

    if (
        certification.provider_key != "api_football"
        or certification.mode != "OFFLINE_REPLAY"
        or certification.request_path != "/fixtures"
    ):
        raise ValueError("OFFLINE_INGEST_CERTIFICATION_SCOPE_INVALID")

    if (
        certification.real_provider_execution_authorized is not False
        or certification.automatic_provider_switch is not False
        or certification.automatic_wagering is not False
        or certification.zero_network_topology_verified is not True
        or certification.zero_network_calls is not True
    ):
        raise ValueError("OFFLINE_INGEST_CERTIFICATION_SAFETY_FAILURE")

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
        raise ValueError("OFFLINE_INGEST_CERTIFICATION_STATUS_INVALID")

    return certification


class SQLiteApiFootballOfflineIngestEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.store_identity = (
            _offline_ingest_store_identity(
                self.path
            )
        )

        with self._connect() as connection:
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS api_football_offline_ingest_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                '''
            )

    def require_authoritative_store(
        self,
    ):
        expected_path = (
            _authoritative_offline_ingest_store_path()
        )

        if (
            self.path.expanduser().resolve()
            != expected_path
            or self.store_identity
            != _offline_ingest_store_identity(
                expected_path
            )
        ):
            raise ValueError(
                "OFFLINE_INGEST_AUTHORITATIVE_STORE_REQUIRED"
            )

        return self

    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _rebuild(payload: Mapping[str, Any]) -> ApiFootballOfflineIngestCertification:
        if (
            payload.get("schema")
            != "matrix.api-football-offline-ingest-certification/3"
        ):
            raise ValueError("OFFLINE_INGEST_EVIDENCE_SCHEMA_INVALID")

        return ApiFootballOfflineIngestCertification(
            evidence_id=str(payload["evidence_id"]),
            status=str(payload["status"]),
            provider_key=str(payload["provider_key"]),
            mode=str(payload["mode"]),
            date=str(payload["date"]),
            source_payload_fingerprint=str(payload["source_payload_fingerprint"]),
            shadow_request_evidence_id=str(payload["shadow_request_evidence_id"]),
            parent_readiness_evidence_id=(
                None
                if payload.get("parent_readiness_evidence_id") is None
                else str(payload["parent_readiness_evidence_id"])
            ),
            request_contract_id=str(payload["request_contract_id"]),
            endpoint_manifest_id=str(payload["endpoint_manifest_id"]),
            authorization_fingerprint=str(payload["authorization_fingerprint"]),
            request_path=str(payload["request_path"]),
            parameter_names=tuple(str(value) for value in payload["parameter_names"]),
            parameter_values_fingerprint=str(
                payload["parameter_values_fingerprint"]
            ),
            code_fingerprint=str(payload["code_fingerprint"]),
            source_revision=str(payload["source_revision"]),
            received_count=int(payload["received_count"]),
            accepted_count=int(payload["accepted_count"]),
            rejected_count=int(payload["rejected_count"]),
            replay_request_count=int(payload["replay_request_count"]),
            reconciliation_call_count=int(payload["reconciliation_call_count"]),
            repository_idempotent=bool(payload["repository_idempotent"]),
            zero_network_topology_verified=bool(
                payload["zero_network_topology_verified"]
            ),
            zero_network_calls=bool(payload["zero_network_calls"]),
            real_provider_execution_authorized=bool(
                payload["real_provider_execution_authorized"]
            ),
            automatic_provider_switch=bool(payload["automatic_provider_switch"]),
            automatic_wagering=bool(payload["automatic_wagering"]),
            blockers=tuple(str(value) for value in payload["blockers"]),
            created_at=str(payload["created_at"]),
            store_identity=str(payload["store_identity"]),
            attestation_key_reference_fingerprint=str(
                payload["attestation_key_reference_fingerprint"]
            ),
            certification_fingerprint=str(payload["certification_fingerprint"]),
            issuer_attestation=str(payload["issuer_attestation"]),
        )

    def record(
        self,
        evidence: ApiFootballOfflineIngestCertification,
    ) -> ApiFootballOfflineIngestCertification:
        verified = verify_api_football_offline_ingest_certification(evidence)

        if verified.store_identity != self.store_identity:
            raise ValueError("OFFLINE_INGEST_STORE_IDENTITY_MISMATCH")

        payload_json = _json(verified.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute(
                '''
                INSERT OR IGNORE INTO api_football_offline_ingest_evidence
                (evidence_id, payload_json, payload_sha256)
                VALUES (?, ?, ?)
                ''',
                (verified.evidence_id, payload_json, payload_sha),
            )

        stored = self.get_verified(verified.evidence_id)
        if stored != verified:
            raise ValueError("OFFLINE_INGEST_DURABLE_RECORD_MISMATCH")
        return verified

    def get_verified(
        self,
        evidence_id: str,
    ) -> ApiFootballOfflineIngestCertification | None:
        with self._connect() as connection:
            row = connection.execute(
                '''
                SELECT payload_json, payload_sha256
                FROM api_football_offline_ingest_evidence
                WHERE evidence_id = ?
                ''',
                (evidence_id,),
            ).fetchone()

        if row is None:
            return None

        payload_json, payload_sha = row
        if sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha:
            raise ValueError("OFFLINE_INGEST_EVIDENCE_STORAGE_INTEGRITY_FAILURE")

        payload = json.loads(payload_json)
        rebuilt = self._rebuild(payload)
        if (
            rebuilt.evidence_id != evidence_id
            or rebuilt.store_identity != self.store_identity
        ):
            raise ValueError("OFFLINE_INGEST_EVIDENCE_REDERIVATION_FAILURE")

        return verify_api_football_offline_ingest_certification(rebuilt)

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            evidence_ids = [
                str(row[0])
                for row in connection.execute(
                    '''
                    SELECT evidence_id
                    FROM api_football_offline_ingest_evidence
                    ORDER BY evidence_id
                    '''
                ).fetchall()
            ]

        try:
            return all(
                self.get_verified(evidence_id) is not None
                for evidence_id in evidence_ids
            )
        except Exception:
            return False


def certify_api_football_offline_fixture_ingest(
    *,
    payload: Mapping[str, Any],
    date: str,
    shadow_evidence_store: SQLiteProviderShadowRehearsalEvidenceStore,
    shadow_request_evidence_id: str,
    evidence_store: SQLiteApiFootballOfflineIngestEvidenceStore,
    clock=lambda: datetime.now(timezone.utc),
) -> ApiFootballOfflineIngestCertification:
    canonical_date = _canonical_date(
        date
    )

    if (
        type(evidence_store)
        is not SQLiteApiFootballOfflineIngestEvidenceStore
    ):
        raise ValueError(
            "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_STORE_REQUIRED"
        )

    evidence_store.require_authoritative_store()

    envelope = (
        validate_api_football_response_envelope(
            payload,
            endpoint="/fixtures",
        )
    )

    payload_parameters = payload.get(
        "parameters"
    )

    if (
        not isinstance(
            payload_parameters,
            Mapping,
        )
        or dict(
            payload_parameters
        )
        != {
            "date": canonical_date,
        }
    ):
        raise ValueError(
            "OFFLINE_INGEST_PAYLOAD_DATE_MISMATCH"
        )

    provenance = (
        _verified_shadow_request_provenance(
            shadow_evidence_store,
            shadow_request_evidence_id,
            canonical_date=canonical_date,
        )
    )

    code_fingerprint = (
        _offline_topology_fingerprint()
    )

    revision = _source_revision()

    replay_client = _OfflineReplayClient(
        payload=payload,
        date=canonical_date,
    )

    blockers: list[str] = []

    with TemporaryDirectory(
        prefix="matrix-api-football-replay-"
    ) as directory:
        repository_path = (
            Path(directory)
            / "football-fixtures.json"
        )

        repository = (
            _TrackingFootballMatchRepository(
                repository_path
            )
        )

        first_records = (
            sync_football_fixtures(
                replay_client,
                repository,
                canonical_date,
            )
        )

        first_bytes = (
            repository_path.read_bytes()
            if repository_path.exists()
            else b""
        )

        second_records = (
            sync_football_fixtures(
                replay_client,
                repository,
                canonical_date,
            )
        )

        second_bytes = (
            repository_path.read_bytes()
            if repository_path.exists()
            else b""
        )

    received_count = len(
        envelope.response
    )

    accepted_count = len(
        first_records
    )

    rejected_count = max(
        0,
        received_count
        - accepted_count,
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
        first_bytes
        == second_bytes
        and first_identities
        == second_identities
    )

    if rejected_count != 0:
        blockers.append(
            "OFFLINE_REPLAY_RECORD_REJECTIONS_PRESENT"
        )

    if replay_client.request_count != 2:
        blockers.append(
            "OFFLINE_REPLAY_REQUEST_COUNT_INVALID"
        )

    if (
        repository.reconciliation_call_count
        != 2
    ):
        blockers.append(
            "OFFLINE_REPLAY_RECONCILIATION_REQUIRED"
        )

    if not repository_idempotent:
        blockers.append(
            "OFFLINE_REPLAY_REPOSITORY_NOT_IDEMPOTENT"
        )

    zero_network_topology_verified = True
    zero_network_calls = (
        zero_network_topology_verified
    )

    status = (
        "CERTIFIED"
        if not blockers
        else "NOT_CERTIFIED"
    )

    created_at = _aware_iso(
        clock()
    )

    reference = (
        build_provider_shadow_attestation_key_reference()
    )

    base_values = {
        "evidence_id": "",
        "status": status,
        "provider_key": "api_football",
        "mode": "OFFLINE_REPLAY",
        "date": canonical_date,
        "source_payload_fingerprint": (
            envelope.payload_fingerprint
        ),
        **provenance,
        "code_fingerprint": (
            code_fingerprint
        ),
        "source_revision": revision,
        "received_count": received_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "replay_request_count": (
            replay_client.request_count
        ),
        "reconciliation_call_count": (
            repository.reconciliation_call_count
        ),
        "repository_idempotent": (
            repository_idempotent
        ),
        "zero_network_topology_verified": (
            zero_network_topology_verified
        ),
        "zero_network_calls": (
            zero_network_calls
        ),
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "blockers": tuple(
            blockers
        ),
        "created_at": created_at,
        "store_identity": (
            evidence_store.store_identity
        ),
        "attestation_key_reference_fingerprint": (
            reference.reference_fingerprint
        ),
        "certification_fingerprint": "",
        "issuer_attestation": "",
    }

    draft = (
        ApiFootballOfflineIngestCertification(
            **base_values
        )
    )

    core = draft.core_payload()

    certification_fingerprint = _sha(
        {
            "schema": (
                "matrix.api-football-offline-ingest-certification-fingerprint/3"
            ),
            "core_payload": core,
        }
    )

    (
        attestation_reference_fingerprint,
        issuer_attestation,
    ) = _certification_attestation(
        core,
        certification_fingerprint,
    )

    evidence_id = _sha(
        {
            "schema": (
                "matrix.api-football-offline-ingest-evidence-id/3"
            ),
            "certification_fingerprint": (
                certification_fingerprint
            ),
            "issuer_attestation": (
                issuer_attestation
            ),
        }
    )

    certification = (
        ApiFootballOfflineIngestCertification(
            **{
                **base_values,
                "evidence_id": (
                    evidence_id
                ),
                "attestation_key_reference_fingerprint": (
                    attestation_reference_fingerprint
                ),
                "certification_fingerprint": (
                    certification_fingerprint
                ),
                "issuer_attestation": (
                    issuer_attestation
                ),
            }
        )
    )

    evidence_store.record(
        certification
    )

    stored = evidence_store.get_verified(
        evidence_id
    )

    if stored is None:
        raise ValueError(
            "OFFLINE_INGEST_DURABLE_EVIDENCE_REQUIRED"
        )

    return stored


def require_api_football_offline_ingest_certified(
    certification: ApiFootballOfflineIngestCertification,
    *,
    evidence_store: SQLiteApiFootballOfflineIngestEvidenceStore,
) -> None:
    if (
        type(evidence_store)
        is not SQLiteApiFootballOfflineIngestEvidenceStore
    ):
        raise ValueError(
            "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_STORE_REQUIRED"
        )

    evidence_store.require_authoritative_store()

    stored = evidence_store.get_verified(
        certification.evidence_id
    )

    if (
        stored is None
        or stored != certification
    ):
        raise ValueError(
            "OFFLINE_INGEST_DURABLE_EVIDENCE_REQUIRED"
        )

    verified = (
        verify_api_football_offline_ingest_certification(
            stored
        )
    )

    if (
        verified.status
        != "CERTIFIED"
    ):
        raise ValueError(
            "OFFLINE_INGEST_CERTIFICATION_REQUIRED"
        )
