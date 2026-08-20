from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3

import pytest

from app.core.provider_network_execution_authorization import (
    ProviderNetworkPermit,
    SQLiteProviderNetworkPermitStore,
    _sha,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _permit() -> ProviderNetworkPermit:
    base = {
        "schema": "matrix.provider-network-permit-id/1",
        "run_id": "run-1",
        "sport": "football",
        "provider_key": "api_football",
        "mode": "PRODUCTION",
        "request_nonce": "call-1",
        "method": "GET",
        "endpoint_manifest_id": "1" * 64,
        "endpoint_authorization_fingerprint": "2" * 64,
        "dns_resolution_fingerprint": "3" * 64,
        "resolved_ips": ["8.8.8.8"],
        "execution_authorization_fingerprint": "4" * 64,
        "security_decision_fingerprint": "5" * 64,
        "security_evidence_id": "6" * 64,
        "issued_at": NOW.isoformat(),
        "one_use": True,
    }

    return ProviderNetworkPermit(
        permit_id=_sha(base),
        run_id="run-1",
        sport="football",
        provider_key="api_football",
        mode="PRODUCTION",
        request_nonce="call-1",
        method="GET",
        endpoint_manifest_id="1" * 64,
        endpoint_authorization_fingerprint="2" * 64,
        dns_resolution_fingerprint="3" * 64,
        resolved_ips=("8.8.8.8",),
        execution_authorization_fingerprint="4" * 64,
        security_decision_fingerprint="5" * 64,
        security_evidence_id="6" * 64,
        issued_at=NOW,
    )


def test_network_permit_store_rederives_semantics_and_audits(tmp_path):
    db_path = tmp_path / "permit.db"
    store = SQLiteProviderNetworkPermitStore(db_path)
    permit = _permit()

    store.issue(permit)
    assert store.audit_integrity() is True

    payload = store.consume(
        permit_id=permit.permit_id,
        consumed_at=NOW,
    )

    assert payload["resolved_ips"] == ["8.8.8.8"]
    assert store.audit_integrity() is True


def test_forged_permit_payload_and_hash_still_fail_semantic_audit(
    tmp_path,
):
    db_path = tmp_path / "permit.db"
    store = SQLiteProviderNetworkPermitStore(db_path)
    permit = _permit()
    store.issue(permit)

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM network_permit "
            "WHERE permit_id = ?",
            (permit.permit_id,),
        ).fetchone()

        payload = json.loads(row[0])
        payload["resolved_ips"] = ["1.1.1.1"]

        forged_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

        forged_sha = sha256(
            forged_json.encode("utf-8")
        ).hexdigest()

        connection.execute(
            "UPDATE network_permit "
            "SET payload_json = ?, payload_sha256 = ? "
            "WHERE permit_id = ?",
            (
                forged_json,
                forged_sha,
                permit.permit_id,
            ),
        )
        connection.commit()

    assert store.audit_integrity() is False

    with pytest.raises(
        ValueError,
        match="NETWORK_PERMIT_REDERIVATION_FAILURE",
    ):
        store.consume(
            permit_id=permit.permit_id,
            consumed_at=NOW,
        )
