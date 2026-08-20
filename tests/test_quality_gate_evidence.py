import sqlite3

from app.core.quality_gate_evidence import (
    SQLiteQualityGatePassEvidenceStore,
)


def test_quality_gate_evidence_is_verified(
    tmp_path,
):
    store = SQLiteQualityGatePassEvidenceStore(
        tmp_path / "gate.db"
    )
    evidence = store.build(
        commit_sha="a" * 40,
        policy_fingerprint="b" * 64,
        dependency_inventory_fingerprint=(
            "c" * 64
        ),
    )

    evidence_id = store.record(
        evidence
    )

    assert (
        store.get_verified(
            evidence_id
        )
        == evidence
    )


def test_quality_gate_evidence_tamper_fails_closed(
    tmp_path,
):
    path = tmp_path / "gate.db"
    store = SQLiteQualityGatePassEvidenceStore(
        path
    )
    evidence = store.build(
        commit_sha="a" * 40,
        policy_fingerprint="b" * 64,
        dependency_inventory_fingerprint=(
            "c" * 64
        ),
    )
    store.record(evidence)

    with sqlite3.connect(
        path
    ) as connection:
        connection.execute(
            """
            UPDATE quality_gate_pass_evidence
            SET policy_fingerprint = ?
            WHERE evidence_id = ?
            """,
            (
                "d" * 64,
                evidence.evidence_id,
            ),
        )
        connection.commit()

    try:
        store.get_verified(
            evidence.evidence_id
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "tampering must fail closed"
        )
