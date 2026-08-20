from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3

from app.core.provider_endpoint_authorization import (
    SQLiteProviderEndpointAuthorizationRegistry,
    build_provider_endpoint_manifest,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def test_endpoint_audit_rederives_semantics_not_only_payload_hash(tmp_path):
    db_path = tmp_path / "endpoint.db"
    registry = SQLiteProviderEndpointAuthorizationRegistry(db_path)

    manifest = build_provider_endpoint_manifest(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        allowed_query_keys=("date",),
        secret_reference_fingerprint="a" * 64,
        valid_from=NOW,
    )
    registry.register(manifest)

    assert registry.audit_integrity() is True

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT manifest_id, payload_json FROM endpoint_manifest"
        ).fetchone()
        manifest_id = str(row[0])
        payload = json.loads(row[1])
        payload["host"] = "evil.example.test"

        forged_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        forged_sha = sha256(forged_json.encode("utf-8")).hexdigest()

        connection.execute(
            "UPDATE endpoint_manifest "
            "SET payload_json = ?, payload_sha256 = ? "
            "WHERE manifest_id = ?",
            (forged_json, forged_sha, manifest_id),
        )
        connection.commit()

    assert registry.audit_integrity() is False
