from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


def _json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _json(value).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class ProviderContractEndpointBinding:
    binding_id: str
    provider_key: str
    sport: str
    request_contract_id: str
    endpoint_manifest_id: str
    path: str
    valid_from: datetime
    valid_until: datetime | None

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-contract-endpoint-binding/1"
            ),
            "binding_id": self.binding_id,
            "provider_key": self.provider_key,
            "sport": self.sport,
            "request_contract_id": (
                self.request_contract_id
            ),
            "endpoint_manifest_id": (
                self.endpoint_manifest_id
            ),
            "path": self.path,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": (
                self.valid_until.isoformat()
                if self.valid_until is not None
                else None
            ),
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "real_provider_execution_authorized": False,
        }


def build_provider_contract_endpoint_binding(
    *,
    provider_key: str,
    sport: str,
    request_contract_id: str,
    endpoint_manifest_id: str,
    path: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> ProviderContractEndpointBinding:
    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError("INVALID_ENDPOINT_BINDING_PATH")

    request_contract_id = _hex64(
        "REQUEST_CONTRACT_ID",
        request_contract_id,
    )
    endpoint_manifest_id = _hex64(
        "ENDPOINT_MANIFEST_ID",
        endpoint_manifest_id,
    )
    valid_from = _aware(valid_from)

    if valid_until is not None:
        valid_until = _aware(valid_until)
        if valid_until <= valid_from:
            raise ValueError(
                "INVALID_ENDPOINT_BINDING_VALIDITY"
            )

    base = {
        "schema": (
            "matrix.provider-contract-endpoint-binding-id/1"
        ),
        "provider_key": provider_key,
        "sport": sport,
        "request_contract_id": request_contract_id,
        "endpoint_manifest_id": endpoint_manifest_id,
        "path": path,
        "valid_from": valid_from.isoformat(),
        "valid_until": (
            valid_until.isoformat()
            if valid_until is not None
            else None
        ),
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "real_provider_execution_authorized": False,
    }

    return ProviderContractEndpointBinding(
        binding_id=_sha(base),
        provider_key=provider_key,
        sport=sport,
        request_contract_id=request_contract_id,
        endpoint_manifest_id=endpoint_manifest_id,
        path=path,
        valid_from=valid_from,
        valid_until=valid_until,
    )


class SQLiteProviderContractEndpointBindingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_contract_endpoint_binding (
                    binding_id TEXT PRIMARY KEY,
                    request_contract_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute(
            "PRAGMA journal_mode = WAL"
        )
        connection.execute(
            "PRAGMA synchronous = FULL"
        )
        return connection

    def register(
        self,
        binding: ProviderContractEndpointBinding,
    ) -> ProviderContractEndpointBinding:
        rebuilt = build_provider_contract_endpoint_binding(
            provider_key=binding.provider_key,
            sport=binding.sport,
            request_contract_id=binding.request_contract_id,
            endpoint_manifest_id=binding.endpoint_manifest_id,
            path=binding.path,
            valid_from=binding.valid_from,
            valid_until=binding.valid_until,
        )

        if rebuilt != binding:
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_DERIVATION_MISMATCH"
            )

        payload_json = _json(
            binding.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_contract_endpoint_binding (
                    binding_id,
                    request_contract_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    binding.binding_id,
                    binding.request_contract_id,
                    payload_json,
                    payload_sha,
                ),
            )
            row = connection.execute(
                """
                SELECT binding_id, payload_json, payload_sha256
                FROM provider_contract_endpoint_binding
                WHERE request_contract_id = ?
                """,
                (
                    binding.request_contract_id,
                ),
            ).fetchone()

        if row != (
            binding.binding_id,
            payload_json,
            payload_sha,
        ):
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_MUTATION_VIOLATION"
            )

        return binding

    def get_verified_by_contract(
        self,
        request_contract_id: str,
    ) -> ProviderContractEndpointBinding | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    binding_id,
                    payload_json,
                    payload_sha256
                FROM provider_contract_endpoint_binding
                WHERE request_contract_id = ?
                """,
                (
                    request_contract_id,
                ),
            ).fetchone()

        if row is None:
            return None

        binding_id, payload_json, payload_sha = row

        if (
            sha256(
                payload_json.encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_INTEGRITY_FAILURE"
            )

        payload = json.loads(
            payload_json
        )

        rebuilt = build_provider_contract_endpoint_binding(
            provider_key=payload["provider_key"],
            sport=payload["sport"],
            request_contract_id=(
                payload["request_contract_id"]
            ),
            endpoint_manifest_id=(
                payload["endpoint_manifest_id"]
            ),
            path=payload["path"],
            valid_from=datetime.fromisoformat(
                payload["valid_from"]
            ),
            valid_until=(
                datetime.fromisoformat(
                    payload["valid_until"]
                )
                if payload.get("valid_until")
                else None
            ),
        )

        if (
            rebuilt.binding_id != binding_id
            or rebuilt.payload() != payload
        ):
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_REDERIVATION_FAILURE"
            )

        return rebuilt

    def authorize(
        self,
        *,
        request_contract_id: str,
        endpoint_manifest_id: str,
        path: str,
        now: datetime,
    ) -> ProviderContractEndpointBinding:
        binding = self.get_verified_by_contract(
            request_contract_id
        )

        if binding is None:
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_NOT_FOUND"
            )

        now = _aware(now)

        if (
            binding.endpoint_manifest_id
            != _hex64(
                "ENDPOINT_MANIFEST_ID",
                endpoint_manifest_id,
            )
            or binding.path != path
        ):
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_MISMATCH"
            )

        if now < binding.valid_from:
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_NOT_ACTIVE"
            )

        if (
            binding.valid_until is not None
            and now >= binding.valid_until
        ):
            raise ValueError(
                "CONTRACT_ENDPOINT_BINDING_EXPIRED"
            )

        return binding

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            contract_ids = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT request_contract_id
                    FROM provider_contract_endpoint_binding
                    ORDER BY request_contract_id
                    """
                ).fetchall()
            ]

        try:
            return all(
                self.get_verified_by_contract(
                    contract_id
                )
                is not None
                for contract_id
                in contract_ids
            )
        except ValueError:
            return False
