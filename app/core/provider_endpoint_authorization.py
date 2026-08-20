from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("NAIVE_DATETIME")
    return value.astimezone(timezone.utc)


def _key(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip().lower()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


_SENSITIVE_QUERY = (
    "key",
    "token",
    "secret",
    "password",
    "authorization",
    "credential",
)


def _normalized_query_keys(
    values: Sequence[str],
    *,
    reject_sensitive: bool,
) -> tuple[str, ...]:
    result = tuple(
        sorted({_key("QUERY_KEY", value) for value in values})
    )
    if reject_sensitive and any(
        fragment in item
        for item in result
        for fragment in _SENSITIVE_QUERY
    ):
        raise ValueError("SENSITIVE_QUERY_KEY_NOT_ALLOWED")
    return result


@dataclass(frozen=True)
class ProviderEndpointManifest:
    provider_key: str
    sport: str
    method: str
    host: str
    port: int
    path: str
    allowed_query_keys: tuple[str, ...]
    secret_reference_fingerprint: str
    valid_from: datetime
    valid_until: datetime | None
    manifest_id: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-endpoint-manifest/1",
            "provider_key": self.provider_key,
            "sport": self.sport,
            "method": self.method,
            "scheme": "https",
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "allowed_query_keys": list(self.allowed_query_keys),
            "secret_reference_fingerprint": self.secret_reference_fingerprint,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": (
                self.valid_until.isoformat()
                if self.valid_until
                else None
            ),
            "automatic_provider_switch": False,
            "manifest_id": self.manifest_id,
        }


@dataclass(frozen=True)
class ProviderEndpointAuthorizationDecision:
    status: str
    executable: bool
    manifest_id: str | None
    endpoint_target_fingerprint: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def build_provider_endpoint_manifest(
    *,
    provider_key: str,
    sport: str,
    method: str,
    endpoint_url: str,
    allowed_query_keys: Sequence[str],
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> ProviderEndpointManifest:
    provider_key = _key("PROVIDER_KEY", provider_key)
    sport = _key("SPORT", sport)
    method = _key("METHOD", method).upper()
    secret_reference_fingerprint = _hex64(
        "SECRET_REFERENCE_FINGERPRINT",
        secret_reference_fingerprint,
    )
    valid_from = _aware(valid_from)
    if valid_until is not None:
        valid_until = _aware(valid_until)
        if valid_until <= valid_from:
            raise ValueError("INVALID_VALIDITY_WINDOW")

    parsed = urlsplit(endpoint_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("HTTPS_REQUIRED")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("UNSAFE_MANIFEST_URL")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("MISSING_HOST")

    port = parsed.port or 443
    if port != 443:
        raise ValueError("TLS_443_REQUIRED")

    path = parsed.path or "/"
    if not path.startswith("/") or ".." in path.split("/"):
        raise ValueError("INVALID_PATH")

    allowed = _normalized_query_keys(
        allowed_query_keys,
        reject_sensitive=True,
    )

    base = {
        "schema": "matrix.provider-endpoint-manifest-id/1",
        "provider_key": provider_key,
        "sport": sport,
        "method": method,
        "scheme": "https",
        "host": host,
        "port": port,
        "path": path,
        "allowed_query_keys": list(allowed),
        "secret_reference_fingerprint": secret_reference_fingerprint,
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until else None,
        "automatic_provider_switch": False,
    }

    return ProviderEndpointManifest(
        provider_key=provider_key,
        sport=sport,
        method=method,
        host=host,
        port=port,
        path=path,
        allowed_query_keys=allowed,
        secret_reference_fingerprint=secret_reference_fingerprint,
        valid_from=valid_from,
        valid_until=valid_until,
        manifest_id=_sha(base),
    )


class SQLiteProviderEndpointAuthorizationRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS endpoint_manifest (
                    manifest_id TEXT PRIMARY KEY,
                    provider_key TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    method TEXT NOT NULL,
                    host TEXT NOT NULL,
                    path TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS endpoint_revocation (
                    manifest_id TEXT PRIMARY KEY,
                    revoked_at TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def register(self, manifest: ProviderEndpointManifest) -> str:
        expected = build_provider_endpoint_manifest(
            provider_key=manifest.provider_key,
            sport=manifest.sport,
            method=manifest.method,
            endpoint_url=f"https://{manifest.host}{manifest.path}",
            allowed_query_keys=manifest.allowed_query_keys,
            secret_reference_fingerprint=manifest.secret_reference_fingerprint,
            valid_from=manifest.valid_from,
            valid_until=manifest.valid_until,
        )
        if expected != manifest:
            raise ValueError("ENDPOINT_MANIFEST_DERIVATION_MISMATCH")

        payload_json = _json(manifest.payload())
        payload_sha = sha256(payload_json.encode()).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_sha256 FROM endpoint_manifest WHERE manifest_id = ?",
                (manifest.manifest_id,),
            ).fetchone()
            if row is not None:
                connection.execute("ROLLBACK")
                if str(row[0]) == payload_sha:
                    return manifest.manifest_id
                raise ValueError("ENDPOINT_MANIFEST_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO endpoint_manifest
                (manifest_id, provider_key, sport, method, host, path, payload_json, payload_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.manifest_id,
                    manifest.provider_key,
                    manifest.sport,
                    manifest.method,
                    manifest.host,
                    manifest.path,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")
        return manifest.manifest_id

    def revoke(
        self,
        *,
        manifest_id: str,
        revoked_at: datetime,
        reason_code: str,
    ) -> str:
        manifest_id = _hex64("MANIFEST_ID", manifest_id)
        revoked_at = _aware(revoked_at)
        reason_code = _key("REASON_CODE", reason_code)
        fp = _sha(
            {
                "schema": "matrix.provider-endpoint-revocation/1",
                "manifest_id": manifest_id,
                "revoked_at": revoked_at.isoformat(),
                "reason_code": reason_code,
            }
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM endpoint_manifest WHERE manifest_id = ?",
                (manifest_id,),
            ).fetchone() is None:
                connection.execute("ROLLBACK")
                raise ValueError("UNKNOWN_ENDPOINT_MANIFEST")

            row = connection.execute(
                "SELECT fingerprint FROM endpoint_revocation WHERE manifest_id = ?",
                (manifest_id,),
            ).fetchone()
            if row is not None:
                connection.execute("ROLLBACK")
                if str(row[0]) == fp:
                    return fp
                raise ValueError("ENDPOINT_REVOCATION_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO endpoint_revocation
                (manifest_id, revoked_at, reason_code, fingerprint)
                VALUES (?, ?, ?, ?)
                """,
                (manifest_id, revoked_at.isoformat(), reason_code, fp),
            )
            connection.execute("COMMIT")
        return fp

    def authorize_request(
        self,
        *,
        provider_key: str,
        sport: str,
        method: str,
        endpoint_url: str,
        query_keys: Sequence[str],
        secret_reference_fingerprint: str,
        as_of: datetime,
    ) -> ProviderEndpointAuthorizationDecision:
        provider_key = _key("PROVIDER_KEY", provider_key)
        sport = _key("SPORT", sport)
        method = _key("METHOD", method).upper()
        secret_reference_fingerprint = _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            secret_reference_fingerprint,
        )
        as_of = _aware(as_of)
        reasons: list[str] = []

        parsed = urlsplit(endpoint_url)
        host = (parsed.hostname or "").lower()
        port = parsed.port or 443
        path = parsed.path or "/"

        raw_query_keys = tuple(
            str(key).lower() for key in query_keys
        ) + tuple(
            key.lower()
            for key, _ in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
        )

        try:
            normalized_keys = _normalized_query_keys(
                raw_query_keys,
                reject_sensitive=True,
            )
        except ValueError:
            normalized_keys = tuple(sorted(set(raw_query_keys)))
            reasons.append("SENSITIVE_QUERY_KEY_NOT_ALLOWED")

        if parsed.scheme.lower() != "https":
            reasons.append("HTTPS_REQUIRED")
        if parsed.username or parsed.password or parsed.fragment:
            reasons.append("UNSAFE_ENDPOINT_URL")
        if port != 443:
            reasons.append("TLS_443_REQUIRED")

        target_fp = _sha(
            {
                "schema": "matrix.provider-endpoint-target/1",
                "scheme": parsed.scheme.lower(),
                "host": host,
                "port": port,
                "path": path,
                "query_keys": list(normalized_keys),
            }
        )

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT m.manifest_id, m.payload_json, m.payload_sha256, r.manifest_id
                FROM endpoint_manifest AS m
                LEFT JOIN endpoint_revocation AS r
                    ON r.manifest_id = m.manifest_id
                WHERE m.provider_key = ?
                  AND m.sport = ?
                  AND m.method = ?
                  AND m.host = ?
                  AND m.path = ?
                ORDER BY m.manifest_id
                """,
                (provider_key, sport, method, host, path),
            ).fetchall()

        matched: str | None = None

        for manifest_id, payload_json, payload_sha, revoked in rows:
            if revoked is not None:
                continue
            if sha256(payload_json.encode()).hexdigest() != payload_sha:
                reasons.append("MANIFEST_INTEGRITY_FAILURE")
                continue

            payload = json.loads(payload_json)
            valid_from = datetime.fromisoformat(payload["valid_from"])
            valid_until = (
                datetime.fromisoformat(payload["valid_until"])
                if payload["valid_until"]
                else None
            )
            if as_of < valid_from:
                continue
            if valid_until is not None and as_of >= valid_until:
                continue
            if payload["secret_reference_fingerprint"] != secret_reference_fingerprint:
                continue
            if not set(normalized_keys).issubset(set(payload["allowed_query_keys"])):
                continue
            matched = str(manifest_id)
            break

        if matched is None:
            reasons.append("NO_ACTIVE_ENDPOINT_CONTRACT")

        reasons = sorted(set(reasons))
        status = "AUTHORIZED" if not reasons else "QUARANTINE"

        base = {
            "schema": "matrix.provider-endpoint-authorization/1",
            "status": status,
            "executable": status == "AUTHORIZED",
            "manifest_id": matched,
            "endpoint_target_fingerprint": target_fp,
            "reason_codes": reasons,
        }

        return ProviderEndpointAuthorizationDecision(
            status=status,
            executable=status == "AUTHORIZED",
            manifest_id=matched,
            endpoint_target_fingerprint=target_fp,
            reason_codes=tuple(reasons),
            decision_fingerprint=_sha(base),
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT manifest_id, payload_json, payload_sha256 "
                "FROM endpoint_manifest ORDER BY manifest_id"
            ).fetchall()
            revocations = connection.execute(
                "SELECT manifest_id, revoked_at, reason_code, fingerprint "
                "FROM endpoint_revocation ORDER BY manifest_id"
            ).fetchall()

        known_manifest_ids: set[str] = set()

        for manifest_id, payload_json, payload_sha in rows:
            manifest_id = str(manifest_id)
            known_manifest_ids.add(manifest_id)

            if sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha:
                return False

            try:
                payload = json.loads(payload_json)

                if payload.get("manifest_id") != manifest_id:
                    return False
                if payload.get("schema") != "matrix.provider-endpoint-manifest/1":
                    return False
                if payload.get("scheme") != "https":
                    return False

                valid_from = datetime.fromisoformat(payload["valid_from"])
                valid_until = (
                    datetime.fromisoformat(payload["valid_until"])
                    if payload.get("valid_until")
                    else None
                )

                rebuilt = build_provider_endpoint_manifest(
                    provider_key=payload["provider_key"],
                    sport=payload["sport"],
                    method=payload["method"],
                    endpoint_url=(
                        "https://"
                        f"{payload['host']}"
                        f"{payload['path']}"
                    ),
                    allowed_query_keys=tuple(payload["allowed_query_keys"]),
                    secret_reference_fingerprint=payload[
                        "secret_reference_fingerprint"
                    ],
                    valid_from=valid_from,
                    valid_until=valid_until,
                )
            except Exception:
                return False

            if rebuilt.manifest_id != manifest_id:
                return False

            if rebuilt.payload() != payload:
                return False

        for manifest_id, revoked_at, reason_code, fp in revocations:
            if str(manifest_id) not in known_manifest_ids:
                return False

            expected = _sha(
                {
                    "schema": "matrix.provider-endpoint-revocation/1",
                    "manifest_id": manifest_id,
                    "revoked_at": revoked_at,
                    "reason_code": reason_code,
                }
            )

            if expected != fp:
                return False

        return True
