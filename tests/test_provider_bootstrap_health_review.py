import json
import sqlite3

import pytest

from app.core.provider_bootstrap_health_review import (
    SQLiteBootstrapHealthReviewStore,
)


def review(
    store,
):
    return store.build_review(
        sport="tennis",
        provider_key="provider-x",
        bootstrap_run_id="boot-run-1",
        reconciliation_fingerprint=(
            "a" * 64
        ),
        runtime_admission_evidence_fingerprint=(
            "b" * 64
        ),
        reviewer_id=(
            "OPS-REVIEWER-1"
        ),
        decision=(
            "KEEP_QUARANTINED"
        ),
    )


def test_bootstrap_health_review_is_manual_and_durable(
    tmp_path,
):
    store = (
        SQLiteBootstrapHealthReviewStore(
            tmp_path / "review.db"
        )
    )
    value = review(store)

    store.record(value)
    replay = store.record(value)

    assert (
        replay.review_id
        == value.review_id
    )
    assert (
        value.payload()[
            "automatic_health_promotion"
        ]
        is False
    )

    loaded = store.get_by_run(
        "boot-run-1"
    )
    assert (
        loaded["review_id"]
        == value.review_id
    )


def test_rehashed_bootstrap_review_tamper_fails_closed(
    tmp_path,
):
    path = tmp_path / "review.db"
    store = (
        SQLiteBootstrapHealthReviewStore(
            path
        )
    )
    value = review(store)
    store.record(value)

    with sqlite3.connect(
        path
    ) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json
                FROM bootstrap_health_reviews
                WHERE bootstrap_run_id = ?
                """,
                (
                    value
                    .bootstrap_run_id,
                ),
            ).fetchone()[0]
        )

        payload["decision"] = (
            "APPROVE_PRODUCTION"
        )

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
            UPDATE bootstrap_health_reviews
            SET
                payload_json = ?,
                payload_sha256 = ?
            WHERE bootstrap_run_id = ?
            """,
            (
                payload_json,
                payload_sha,
                value
                .bootstrap_run_id,
            ),
        )
        connection.commit()

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_REVIEW_REDERIVATION_MISMATCH",
    ):
        store.get_by_run(
            "boot-run-1"
        )
