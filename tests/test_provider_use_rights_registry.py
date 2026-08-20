from datetime import datetime, timezone
import json
import sqlite3

import pytest

from app.core.provider_use_rights_registry import (
    SQLiteProviderUseRightsRegistry,
)


UTC = timezone.utc


def manifest(registry):
    return registry.build_manifest(
        sport="tennis",
        provider_key="provider-x",
        data_scope=(
            "fixtures",
            "history",
        ),
        allowed_purposes=(
            "analysis",
        ),
        jurisdiction_scope=(
            "CO",
        ),
        effective_at=datetime(
            2026,
            8,
            1,
            tzinfo=UTC,
        ),
        expires_at=None,
        terms_reference_sha256=(
            "a" * 64
        ),
        manual_approval_id=(
            "LEGAL-001"
        ),
        status="APPROVED",
    )


def test_use_rights_manifest_is_manual_and_immutable(
    tmp_path,
):
    registry = (
        SQLiteProviderUseRightsRegistry(
            tmp_path / "rights.db"
        )
    )
    value = manifest(registry)

    registry.register(value)
    replay = registry.register(value)

    assert (
        replay.manifest_id
        == value.manifest_id
    )
    assert (
        registry.audit_integrity().ok
        is True
    )


def test_exact_intended_use_must_be_authorized(
    tmp_path,
):
    registry = (
        SQLiteProviderUseRightsRegistry(
            tmp_path / "rights.db"
        )
    )
    value = manifest(registry)
    registry.register(value)

    registry.authorize_use(
        manifest_fingerprint=(
            value.manifest_fingerprint
        ),
        sport="tennis",
        provider_key="provider-x",
        requested_data_scope=(
            "history",
        ),
        requested_purpose="analysis",
        requested_jurisdiction="CO",
        as_of=datetime(
            2026,
            8,
            2,
            tzinfo=UTC,
        ),
    )

    with pytest.raises(
        ValueError,
        match="RIGHTS_DATA_SCOPE_NOT_ALLOWED",
    ):
        registry.authorize_use(
            manifest_fingerprint=(
                value.manifest_fingerprint
            ),
            sport="tennis",
            provider_key="provider-x",
            requested_data_scope=(
                "live_video",
            ),
            requested_purpose="analysis",
            requested_jurisdiction="CO",
            as_of=datetime(
                2026,
                8,
                2,
                tzinfo=UTC,
            ),
        )


def test_semantic_tamper_with_rehashed_payload_fails_closed(
    tmp_path,
):
    path = tmp_path / "rights.db"
    registry = (
        SQLiteProviderUseRightsRegistry(
            path
        )
    )
    value = manifest(registry)
    registry.register(value)

    with sqlite3.connect(
        path
    ) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM provider_use_rights
                WHERE manifest_fingerprint = ?
                """,
                (
                    value
                    .manifest_fingerprint,
                ),
            ).fetchone()[0]
        )

        payload[
            "allowed_purposes"
        ] = ["redistribution"]

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
            UPDATE provider_use_rights
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE manifest_fingerprint = ?
            """,
            (
                payload_json,
                payload_sha,
                value
                .manifest_fingerprint,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="PROVIDER_RIGHTS_REDERIVATION_MISMATCH",
    ):
        registry.get_by_fingerprint(
            value.manifest_fingerprint
        )
