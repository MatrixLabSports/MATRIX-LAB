import hashlib
import json
import sqlite3

from app.core.release_eligibility_evidence import (
    SQLiteReleaseEligibilityEvidenceStore,
    build_release_eligibility_decision,
)


def decision(
    *,
    static_checks_passed=True,
):
    return build_release_eligibility_decision(
        commit_sha="a" * 40,
        policy_fingerprint="b" * 64,
        dependency_inventory_fingerprint=(
            "c" * 64
        ),
        canonical_tests_passed=True,
        static_checks_passed=(
            static_checks_passed
        ),
        security_scan_passed=True,
    )


def test_release_eligibility_requires_every_gate(
    tmp_path,
):
    value = decision()

    assert (
        value.status
        == "ELIGIBLE_FOR_MANUAL_RELEASE"
    )
    assert (
        value.payload()[
            "automatic_deploy"
        ]
        is False
    )

    store = (
        SQLiteReleaseEligibilityEvidenceStore(
            tmp_path / "release.db"
        )
    )

    first = store.record(value)
    second = store.record(value)

    assert first == second
    assert (
        store.audit_integrity().ok
        is True
    )


def test_failed_gate_quarantines_release():
    value = decision(
        static_checks_passed=False,
    )

    assert value.status == "QUARANTINE"


def test_rehashed_release_evidence_tamper_fails_closed(
    tmp_path,
):
    path = tmp_path / "release.db"
    store = (
        SQLiteReleaseEligibilityEvidenceStore(
            path
        )
    )
    value = decision()
    store.record(value)

    with sqlite3.connect(
        path
    ) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM release_eligibility_evidence
                WHERE commit_sha = ?
                """,
                (
                    value.commit_sha,
                ),
            ).fetchone()[0]
        )

        payload[
            "security_scan_passed"
        ] = False

        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

        payload_sha = hashlib.sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        connection.execute(
            """
            UPDATE release_eligibility_evidence
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE commit_sha = ?
            """,
            (
                payload_json,
                payload_sha,
                value.commit_sha,
            ),
        )
        connection.commit()

    assert (
        store.audit_integrity().ok
        is False
    )
