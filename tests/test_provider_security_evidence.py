from types import SimpleNamespace
import sqlite3

from app.core.provider_security_evidence import (
    SQLiteProviderSecurityEvidenceStore,
)
from app.core.provider_security_gate import (
    evaluate_provider_security,
)
from app.core.secret_reference import (
    build_secret_reference,
)


def decision():
    preflight = SimpleNamespace(
        status="EXECUTE",
        executable=True,
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        decision_fingerprint="a" * 64,
    )

    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable=(
            "MATRIX_PROVIDER_X_API_KEY"
        ),
        secret_type="API_KEY",
    )

    return evaluate_provider_security(
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        preflight_decision=preflight,
        endpoint_url=(
            "https://api.provider.example/v1"
        ),
        secret_reference=reference,
    )


def test_security_evidence_is_idempotent_and_auditable(
    tmp_path,
):
    path = tmp_path / "security.db"
    store = (
        SQLiteProviderSecurityEvidenceStore(
            path
        )
    )
    value = decision()

    first = store.record(value)
    second = store.record(value)

    assert first == second
    assert (
        store.audit_integrity().ok
        is True
    )


def test_security_evidence_detects_tampered_id(
    tmp_path,
):
    path = tmp_path / "security.db"
    store = (
        SQLiteProviderSecurityEvidenceStore(
            path
        )
    )
    value = decision()
    store.record(value)

    with sqlite3.connect(
        path
    ) as connection:
        connection.execute(
            """
            UPDATE provider_security_evidence
            SET evidence_id = ?
            WHERE run_id = ?
            """,
            (
                "f" * 64,
                value.run_id,
            ),
        )
        connection.commit()

    assert (
        store.audit_integrity().ok
        is False
    )
