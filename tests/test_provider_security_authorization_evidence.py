import hashlib
import json
import sqlite3

from app.core.provider_preflight_gate import (
    ProviderPreflightDecision,
    SQLiteProviderPreflightEvidenceStore,
    _decision_fingerprint as preflight_fingerprint,
)
from app.core.provider_security_authorization import (
    evaluate_authoritative_provider_security,
)
from app.core.provider_security_authorization_evidence import (
    SQLiteAuthoritativeProviderSecurityEvidenceStore,
)
from app.core.secret_reference import (
    SQLiteSecretReferenceRegistry,
    build_secret_reference,
)


def _decision(tmp_path, monkeypatch):
    values = dict(
        status="EXECUTE",
        executable=True,
        downstream_quarantine_required=False,
        run_id="run-1",
        sport="tennis",
        provider_key="provider-x",
        mode="PRODUCTION",
        queue_fingerprint="a" * 64,
        permit_id="b" * 64,
        rights_manifest_fingerprint="c" * 64,
        scheduling_evidence_fingerprint="d" * 64,
        bootstrap_policy_fingerprint=None,
        requested_data_scope=("history",),
        requested_purpose="analysis",
        requested_jurisdiction="CO",
        max_items=1,
        max_requests=1,
        provider_health_status="ELIGIBLE",
        reason_codes=(),
    )

    preflight = ProviderPreflightDecision(
        **values,
        decision_fingerprint=preflight_fingerprint(
            **values
        ),
    )
    preflight_store = SQLiteProviderPreflightEvidenceStore(
        tmp_path / "preflight.db"
    )
    preflight_store.record(preflight)

    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable=(
            "MATRIX_PROVIDER_X_API_KEY"
        ),
        secret_type="API_KEY",
    )
    registry = SQLiteSecretReferenceRegistry(
        tmp_path / "secret-refs.db"
    )
    registry.register(reference)

    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    return evaluate_authoritative_provider_security(
        run_id="run-1",
        sport="tennis",
        provider_key="provider-x",
        mode="PRODUCTION",
        preflight_decision=preflight,
        preflight_evidence_store=preflight_store,
        endpoint_url=(
            "https://api.provider.example/v1/history"
        ),
        secret_reference=reference,
        secret_reference_registry=registry,
    )


def test_authoritative_security_evidence_is_idempotent_and_auditable(
    tmp_path,
    monkeypatch,
):
    store = (
        SQLiteAuthoritativeProviderSecurityEvidenceStore(
            tmp_path / "security.db"
        )
    )
    decision = _decision(
        tmp_path,
        monkeypatch,
    )

    first = store.record(decision)
    second = store.record(decision)

    assert first == second
    assert store.audit_integrity().ok is True


def test_rehashed_semantic_tamper_fails_closed(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "security.db"
    store = (
        SQLiteAuthoritativeProviderSecurityEvidenceStore(
            path
        )
    )
    decision = _decision(
        tmp_path,
        monkeypatch,
    )
    store.record(decision)

    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM authoritative_provider_security_evidence
                WHERE run_id = ?
                """,
                (decision.run_id,),
            ).fetchone()[0]
        )

        payload[
            "endpoint_target_fingerprint"
        ] = "f" * 64

        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        payload_sha = hashlib.sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        connection.execute(
            """
            UPDATE authoritative_provider_security_evidence
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE run_id = ?
            """,
            (
                payload_json,
                payload_sha,
                decision.run_id,
            ),
        )
        connection.commit()

    assert store.audit_integrity().ok is False


def test_tampered_evidence_id_fails_closed(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "security.db"
    store = (
        SQLiteAuthoritativeProviderSecurityEvidenceStore(
            path
        )
    )
    decision = _decision(
        tmp_path,
        monkeypatch,
    )
    store.record(decision)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE authoritative_provider_security_evidence
            SET evidence_id = ?
            WHERE run_id = ?
            """,
            (
                "f" * 64,
                decision.run_id,
            ),
        )
        connection.commit()

    assert store.audit_integrity().ok is False
