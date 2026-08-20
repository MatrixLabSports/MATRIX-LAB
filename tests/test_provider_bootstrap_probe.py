import json
import sqlite3

import pytest

from app.core.provider_bootstrap_probe import (
    SQLiteBootstrapProbePolicyRegistry,
    build_bootstrap_probe_policy,
)


def policy():
    return build_bootstrap_probe_policy(
        sport="football",
        provider_key="provider-x",
        manual_approval_id="OPS-BOOT-1",
        max_items=3,
        max_requests=5,
    )


def test_bootstrap_probe_is_tiny_manual_and_quarantined():
    value = policy()

    payload = value.payload()

    assert (
        payload["mode"]
        == "BOOTSTRAP_PROBE"
    )
    assert (
        payload[
            "downstream_quarantine_required"
        ]
        is True
    )
    assert (
        payload[
            "automatic_health_promotion"
        ]
        is False
    )


def test_bootstrap_policy_is_durable_and_verified(
    tmp_path,
):
    registry = (
        SQLiteBootstrapProbePolicyRegistry(
            tmp_path / "policy.db"
        )
    )
    value = policy()

    registry.register(value)
    loaded = registry.get_by_fingerprint(
        value.policy_fingerprint
    )

    assert (
        loaded["policy_id"]
        == value.policy_id
    )


def test_rehashed_bootstrap_policy_tamper_fails_closed(
    tmp_path,
):
    path = tmp_path / "policy.db"
    registry = (
        SQLiteBootstrapProbePolicyRegistry(
            path
        )
    )
    value = policy()
    registry.register(value)

    with sqlite3.connect(
        path
    ) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM bootstrap_probe_policies
                WHERE policy_fingerprint = ?
                """,
                (
                    value
                    .policy_fingerprint,
                ),
            ).fetchone()[0]
        )

        payload["max_requests"] = 9

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
            UPDATE bootstrap_probe_policies
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE policy_fingerprint = ?
            """,
            (
                payload_json,
                payload_sha,
                value
                .policy_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_POLICY_REDERIVATION_MISMATCH",
    ):
        registry.get_by_fingerprint(
            value.policy_fingerprint
        )
