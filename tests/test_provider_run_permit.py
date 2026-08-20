import json
import sqlite3

import pytest

from app.core.provider_run_permit import (
    SQLiteProviderRunPermitStore,
)


def permit(
    store,
    run_id="run-1",
):
    return store.build_permit(
        run_id=run_id,
        sport="football",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        queue_fingerprint="a" * 64,
        scheduling_evidence_fingerprint=(
            "b" * 64
        ),
        rights_manifest_fingerprint=(
            "c" * 64
        ),
        bootstrap_policy_fingerprint=(
            "d" * 64
        ),
        max_items=3,
        max_requests=5,
    )


def consume(
    store,
    value,
    *,
    queue_fingerprint="a" * 64,
):
    return store.consume(
        permit_id=value.permit_id,
        run_id=value.run_id,
        sport=value.sport,
        provider_key=(
            value.provider_key
        ),
        mode=value.mode,
        queue_fingerprint=(
            queue_fingerprint
        ),
        scheduling_evidence_fingerprint=(
            value
            .scheduling_evidence_fingerprint
        ),
        rights_manifest_fingerprint=(
            value
            .rights_manifest_fingerprint
        ),
        bootstrap_policy_fingerprint=(
            value
            .bootstrap_policy_fingerprint
        ),
        max_items=value.max_items,
        max_requests=(
            value.max_requests
        ),
    )


def test_run_bound_permit_is_one_use(
    tmp_path,
):
    store = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    value = permit(store)
    store.issue(value)

    consumed = consume(
        store,
        value,
    )

    assert (
        consumed["run_id"]
        == "run-1"
    )

    with pytest.raises(
        ValueError,
        match="PROVIDER_RUN_PERMIT_ALREADY_CONSUMED",
    ):
        consume(
            store,
            value,
        )


def test_run_bound_permit_rejects_queue_replay(
    tmp_path,
):
    store = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    value = permit(store)
    store.issue(value)

    with pytest.raises(
        ValueError,
        match=(
            "PROVIDER_RUN_PERMIT_BINDING_MISMATCH:"
            "queue_fingerprint"
        ),
    ):
        consume(
            store,
            value,
            queue_fingerprint=(
                "e" * 64
            ),
        )


def test_rehashed_permit_tamper_fails_closed(
    tmp_path,
):
    path = tmp_path / "permit.db"
    store = (
        SQLiteProviderRunPermitStore(
            path
        )
    )
    value = permit(store)
    store.issue(value)

    with sqlite3.connect(
        path
    ) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM provider_run_permits
                WHERE permit_id = ?
                """,
                (
                    value.permit_id,
                ),
            ).fetchone()[0]
        )

        payload[
            "max_requests"
        ] = 9

        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

        import hashlib

        payload_sha = hashlib.sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        connection.execute(
            """
            UPDATE provider_run_permits
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE permit_id = ?
            """,
            (
                payload_json,
                payload_sha,
                value.permit_id,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="PROVIDER_RUN_PERMIT_REDERIVATION_MISMATCH",
    ):
        store.get_verified(
            value.permit_id
        )
