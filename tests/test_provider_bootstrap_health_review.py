from app.core.provider_bootstrap_health_review import (
    SQLiteBootstrapHealthReviewStore,
)


def test_bootstrap_health_review_is_manual_and_durable(tmp_path):
    store = SQLiteBootstrapHealthReviewStore(
        tmp_path / "review.db"
    )
    review = store.build_review(
        sport="tennis",
        provider_key="provider-x",
        bootstrap_run_id="boot-run-1",
        reconciliation_fingerprint="a" * 64,
        runtime_admission_evidence_fingerprint="b" * 64,
        reviewer_id="OPS-REVIEWER-1",
        decision="KEEP_QUARANTINED",
    )

    store.record(review)
    replay = store.record(review)

    assert replay.review_id == review.review_id
    assert (
        review.payload()["automatic_health_promotion"]
        is False
    )
