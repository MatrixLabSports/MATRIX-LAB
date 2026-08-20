from app.core.quality_gate_evidence import (
    SQLiteQualityGatePassEvidenceStore,
)
from app.core.release_eligibility_evidence import (
    SQLiteReleaseEligibilityEvidenceStore,
    build_release_eligibility_from_verified_gate,
)


def _gate(
    tmp_path,
    *,
    commit_sha="a" * 40,
):
    store = (
        SQLiteQualityGatePassEvidenceStore(
            tmp_path / "gate.db"
        )
    )
    evidence = store.build(
        commit_sha=commit_sha,
        policy_fingerprint="b" * 64,
        dependency_inventory_fingerprint=(
            "c" * 64
        ),
    )
    store.record(evidence)

    return store, evidence


def test_release_requires_verified_gate(
    tmp_path,
):
    gate_store, gate = _gate(
        tmp_path
    )

    decision = (
        build_release_eligibility_from_verified_gate(
            gate_store=gate_store,
            quality_gate_evidence_id=(
                gate.evidence_id
            ),
            expected_commit_sha="a" * 40,
            expected_policy_fingerprint=(
                "b" * 64
            ),
            expected_dependency_inventory_fingerprint=(
                "c" * 64
            ),
        )
    )

    assert (
        decision.status
        == "ELIGIBLE_FOR_MANUAL_RELEASE"
    )

    release_store = (
        SQLiteReleaseEligibilityEvidenceStore(
            tmp_path / "release.db"
        )
    )

    release_store.record(
        decision
    )

    assert (
        release_store
        .audit_integrity()
        .ok
        is True
    )


def test_commit_mismatch_quarantines(
    tmp_path,
):
    gate_store, gate = _gate(
        tmp_path
    )

    decision = (
        build_release_eligibility_from_verified_gate(
            gate_store=gate_store,
            quality_gate_evidence_id=(
                gate.evidence_id
            ),
            expected_commit_sha="d" * 40,
            expected_policy_fingerprint=(
                "b" * 64
            ),
            expected_dependency_inventory_fingerprint=(
                "c" * 64
            ),
        )
    )

    assert decision.status == "QUARANTINE"
