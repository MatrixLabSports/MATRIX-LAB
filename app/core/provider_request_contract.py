from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


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


def request_parameter_values_fingerprint(
    params: Mapping[str, Any] | None,
) -> str:
    actual = {} if params is None else dict(params)
    normalized = {
        str(name): actual[name]
        for name in sorted(actual, key=lambda item: str(item))
    }
    return _sha(
        {
            "schema": "matrix.provider-request-parameter-values/1",
            "values": normalized,
        }
    )


def build_provider_request_authorization_fingerprint(
    *,
    contract_id: str,
    provider_key: str,
    sport: str,
    method: str,
    path: str,
    parameter_names: Sequence[str],
    parameter_values_fingerprint: str,
    secret_reference_fingerprint: str,
) -> str:
    contract_id = _hex64("REQUEST_CONTRACT_ID", contract_id)
    parameter_values_fingerprint = _hex64(
        "PARAMETER_VALUES_FINGERPRINT",
        parameter_values_fingerprint,
    )
    secret_reference_fingerprint = _hex64(
        "SECRET_REFERENCE_FINGERPRINT",
        secret_reference_fingerprint,
    )

    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")

    method = method.upper()
    if method != "GET":
        raise ValueError("ONLY_GET_AUTHORIZATION_SUPPORTED")
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError("INVALID_REQUEST_AUTHORIZATION_PATH")

    names = tuple(sorted(str(name) for name in parameter_names))
    if len(set(names)) != len(names):
        raise ValueError("DUPLICATE_PARAMETER_NAME")

    return _sha(
        {
            "schema": "matrix.provider-request-authorization/2",
            "contract_id": contract_id,
            "provider_key": provider_key,
            "sport": sport,
            "method": method,
            "path": path,
            "parameter_names": list(names),
            "parameter_values_fingerprint": parameter_values_fingerprint,
            "secret_reference_fingerprint": secret_reference_fingerprint,
            "automatic_provider_switch": False,
        }
    )


@dataclass(frozen=True)
class RequestParameterRule:
    name: str
    value_type: str
    required: bool = False
    minimum: int | None = None
    maximum: int | None = None

    def payload(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "value_type": self.value_type,
            "required": self.required,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class ProviderRequestContract:
    contract_id: str
    provider_key: str
    sport: str
    method: str
    path: str
    parameter_rules: tuple[RequestParameterRule, ...]
    auth_header_name: str
    secret_reference_fingerprint: str
    valid_from: datetime
    valid_until: datetime | None

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-request-contract/1",
            "contract_id": self.contract_id,
            "provider_key": self.provider_key,
            "sport": self.sport,
            "method": self.method,
            "path": self.path,
            "parameter_rules": [rule.payload() for rule in self.parameter_rules],
            "auth_header_name": self.auth_header_name,
            "secret_reference_fingerprint": self.secret_reference_fingerprint,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": (
                self.valid_until.isoformat()
                if self.valid_until is not None
                else None
            ),
            "automatic_provider_switch": False,
        }


@dataclass(frozen=True)
class ProviderRequestAuthorization:
    contract_id: str
    provider_key: str
    sport: str
    method: str
    path: str
    auth_header_name: str
    secret_reference_fingerprint: str
    parameter_names: tuple[str, ...]
    parameter_values_fingerprint: str
    authorization_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-request-authorization-evidence/1",
            "contract_id": self.contract_id,
            "provider_key": self.provider_key,
            "sport": self.sport,
            "method": self.method,
            "path": self.path,
            "auth_header_name": self.auth_header_name,
            "secret_reference_fingerprint": self.secret_reference_fingerprint,
            "parameter_names": list(self.parameter_names),
            "parameter_values_fingerprint": self.parameter_values_fingerprint,
            "authorization_fingerprint": self.authorization_fingerprint,
            "query_values_persisted": False,
            "secret_material_persisted": False,
            "automatic_provider_switch": False,
        }


def build_provider_request_contract(
    *,
    provider_key: str,
    sport: str,
    method: str,
    path: str,
    parameter_rules: Sequence[RequestParameterRule],
    auth_header_name: str,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> ProviderRequestContract:
    if not provider_key or sport not in {"football", "tennis"}:
        raise ValueError("INVALID_REQUEST_CONTRACT_SCOPE")

    method = method.upper()
    if method != "GET":
        raise ValueError("ONLY_GET_CONTRACTS_SUPPORTED")
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError("INVALID_REQUEST_CONTRACT_PATH")
    if not auth_header_name or "\r" in auth_header_name or "\n" in auth_header_name:
        raise ValueError("INVALID_AUTH_HEADER_NAME")

    secret_reference_fingerprint = _hex64(
        "SECRET_REFERENCE_FINGERPRINT",
        secret_reference_fingerprint,
    )

    names: set[str] = set()
    rules: list[RequestParameterRule] = []

    for rule in parameter_rules:
        if not isinstance(rule, RequestParameterRule) or not rule.name or rule.name in names:
            raise ValueError("INVALID_PARAMETER_RULE")
        if rule.value_type not in {"DATE", "POSITIVE_INT", "NONEMPTY_STR"}:
            raise ValueError("INVALID_PARAMETER_TYPE")
        if (
            rule.minimum is not None
            and rule.maximum is not None
            and rule.minimum > rule.maximum
        ):
            raise ValueError("INVALID_PARAMETER_RANGE")
        names.add(rule.name)
        rules.append(rule)

    rules.sort(key=lambda item: item.name)
    valid_from = _aware(valid_from)

    if valid_until is not None:
        valid_until = _aware(valid_until)
        if valid_until <= valid_from:
            raise ValueError("INVALID_CONTRACT_VALIDITY")

    base = {
        "schema": "matrix.provider-request-contract-id/1",
        "provider_key": provider_key,
        "sport": sport,
        "method": method,
        "path": path,
        "parameter_rules": [rule.payload() for rule in rules],
        "auth_header_name": auth_header_name,
        "secret_reference_fingerprint": secret_reference_fingerprint,
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until else None,
        "automatic_provider_switch": False,
    }

    return ProviderRequestContract(
        contract_id=_sha(base),
        provider_key=provider_key,
        sport=sport,
        method=method,
        path=path,
        parameter_rules=tuple(rules),
        auth_header_name=auth_header_name,
        secret_reference_fingerprint=secret_reference_fingerprint,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _validate(rule: RequestParameterRule, value: object) -> None:
    if rule.value_type == "DATE":
        if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
            raise ValueError(f"INVALID_PARAMETER_VALUE:{rule.name}")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(f"INVALID_PARAMETER_VALUE:{rule.name}") from error
        return

    if rule.value_type == "POSITIVE_INT":
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"INVALID_PARAMETER_VALUE:{rule.name}")
        if rule.minimum is not None and value < rule.minimum:
            raise ValueError(f"PARAMETER_BELOW_MINIMUM:{rule.name}")
        if rule.maximum is not None and value > rule.maximum:
            raise ValueError(f"PARAMETER_ABOVE_MAXIMUM:{rule.name}")
        return

    if rule.value_type == "NONEMPTY_STR":
        if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
            raise ValueError(f"INVALID_PARAMETER_VALUE:{rule.name}")
        return

    raise ValueError("UNKNOWN_PARAMETER_TYPE")


class SQLiteProviderRequestContractRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS request_contract ("
                "contract_id TEXT PRIMARY KEY,"
                "payload_json TEXT NOT NULL,"
                "payload_sha256 TEXT NOT NULL)"
            )

    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def register(self, contract: ProviderRequestContract) -> ProviderRequestContract:
        rebuilt = build_provider_request_contract(
            provider_key=contract.provider_key,
            sport=contract.sport,
            method=contract.method,
            path=contract.path,
            parameter_rules=contract.parameter_rules,
            auth_header_name=contract.auth_header_name,
            secret_reference_fingerprint=contract.secret_reference_fingerprint,
            valid_from=contract.valid_from,
            valid_until=contract.valid_until,
        )
        if rebuilt != contract:
            raise ValueError("REQUEST_CONTRACT_DERIVATION_MISMATCH")

        payload_json = _json(contract.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO request_contract "
                "(contract_id, payload_json, payload_sha256) VALUES (?, ?, ?)",
                (contract.contract_id, payload_json, payload_sha),
            )
            row = connection.execute(
                "SELECT payload_json, payload_sha256 "
                "FROM request_contract WHERE contract_id = ?",
                (contract.contract_id,),
            ).fetchone()

        if row != (payload_json, payload_sha):
            raise ValueError("REQUEST_CONTRACT_MUTATION_VIOLATION")
        return contract

    def get_verified(self, contract_id: str) -> ProviderRequestContract | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, payload_sha256 "
                "FROM request_contract WHERE contract_id = ?",
                (contract_id,),
            ).fetchone()

        if row is None:
            return None

        payload_json, payload_sha = row
        if sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha:
            raise ValueError("REQUEST_CONTRACT_INTEGRITY_FAILURE")

        payload = json.loads(payload_json)
        rules = tuple(
            RequestParameterRule(
                name=item["name"],
                value_type=item["value_type"],
                required=bool(item["required"]),
                minimum=item["minimum"],
                maximum=item["maximum"],
            )
            for item in payload["parameter_rules"]
        )

        rebuilt = build_provider_request_contract(
            provider_key=payload["provider_key"],
            sport=payload["sport"],
            method=payload["method"],
            path=payload["path"],
            parameter_rules=rules,
            auth_header_name=payload["auth_header_name"],
            secret_reference_fingerprint=payload["secret_reference_fingerprint"],
            valid_from=datetime.fromisoformat(payload["valid_from"]),
            valid_until=(
                datetime.fromisoformat(payload["valid_until"])
                if payload.get("valid_until")
                else None
            ),
        )

        if rebuilt.contract_id != contract_id or rebuilt.payload() != payload:
            raise ValueError("REQUEST_CONTRACT_REDERIVATION_FAILURE")
        return rebuilt

    def authorize(
        self,
        *,
        contract_id: str,
        provider_key: str,
        sport: str,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        secret_reference_fingerprint: str,
        now: datetime,
    ) -> ProviderRequestAuthorization:
        contract = self.get_verified(contract_id)
        if contract is None:
            raise ValueError("REQUEST_CONTRACT_NOT_FOUND")

        now = _aware(now)
        secret_fp = _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            secret_reference_fingerprint,
        )

        if (
            contract.provider_key != provider_key
            or contract.sport != sport
            or contract.method != method.upper()
            or contract.path != path
            or contract.secret_reference_fingerprint != secret_fp
        ):
            raise ValueError("REQUEST_CONTRACT_BINDING_MISMATCH")

        if now < contract.valid_from:
            raise ValueError("REQUEST_CONTRACT_NOT_ACTIVE")
        if contract.valid_until is not None and now >= contract.valid_until:
            raise ValueError("REQUEST_CONTRACT_EXPIRED")

        actual = {} if params is None else dict(params)
        rules = {rule.name: rule for rule in contract.parameter_rules}

        if set(actual) - set(rules):
            raise ValueError("UNAUTHORIZED_REQUEST_PARAMETER")

        for rule in contract.parameter_rules:
            if rule.required and rule.name not in actual:
                raise ValueError(f"MISSING_REQUIRED_PARAMETER:{rule.name}")
            if rule.name in actual:
                _validate(rule, actual[rule.name])

        names = tuple(sorted(actual))
        values_fingerprint = request_parameter_values_fingerprint(actual)
        authorization_fingerprint = (
            build_provider_request_authorization_fingerprint(
                contract_id=contract.contract_id,
                provider_key=provider_key,
                sport=sport,
                method=method,
                path=path,
                parameter_names=names,
                parameter_values_fingerprint=values_fingerprint,
                secret_reference_fingerprint=contract.secret_reference_fingerprint,
            )
        )

        return ProviderRequestAuthorization(
            contract_id=contract.contract_id,
            provider_key=provider_key,
            sport=sport,
            method=method.upper(),
            path=path,
            auth_header_name=contract.auth_header_name,
            secret_reference_fingerprint=contract.secret_reference_fingerprint,
            parameter_names=names,
            parameter_values_fingerprint=values_fingerprint,
            authorization_fingerprint=authorization_fingerprint,
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT contract_id FROM request_contract ORDER BY contract_id"
                ).fetchall()
            ]

        try:
            return all(self.get_verified(contract_id) is not None for contract_id in ids)
        except ValueError:
            return False
