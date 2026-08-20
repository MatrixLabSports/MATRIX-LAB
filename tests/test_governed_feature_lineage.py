from types import SimpleNamespace
import sqlite3

from app.core.feature_set_manifest_registry import (
    SQLiteFeatureSetManifestRegistry,
)
from app.core.feature_transformation_registry import (
    SQLiteFeatureTransformationRegistry,
    TransformationInput,
)
from app.core.governed_feature_lineage import (
    FeatureLineageEntry,
    FeatureLineageSource,
    SQLiteGovernedFeatureAdmissionEvidence,
    evaluate_governed_feature_snapshot,
)


def setup(tmp_path):
    feature_fp = "a" * 64

    set_registry = SQLiteFeatureSetManifestRegistry(
        tmp_path / "sets.db"
    )
    manifest = set_registry.build_manifest(
        sport="tennis",
        entity_type="player",
        feature_set_key="prematch.core",
        feature_set_version="1",
        feature_definition_fingerprints=(feature_fp,),
    )
    set_registry.register(manifest)

    transform_registry = SQLiteFeatureTransformationRegistry(
        tmp_path / "transforms.db"
    )
    transformation = transform_registry.build_transformation(
        sport="tennis",
        entity_type="player",
        transformation_key="serve.form",
        transformation_version="1",
        artifact_sha256="b" * 64,
        output_feature_definition_fingerprints=(feature_fp,),
        inputs=(
            TransformationInput(
                schema_name="tennis.player.match_history",
                schema_version="1",
                fields=("aces",),
            ),
        ),
    )
    transform_registry.register(transformation)

    snapshot = SimpleNamespace(
        sport="tennis",
        canonical_id="tennis:player:subject",
        feature_set_key="prematch.core",
        feature_set_version="1",
        definition_fingerprints=(feature_fp,),
        source_record_fingerprints=("c" * 64,),
        snapshot_fingerprint="d" * 64,
    )

    lineage = (
        FeatureLineageEntry(
            feature_definition_fingerprint=feature_fp,
            transformation_fingerprint=(
                transformation.transformation_fingerprint
            ),
            sources=(
                FeatureLineageSource(
                    source_record_fingerprint="c" * 64,
                    schema_name="tennis.player.match_history",
                    schema_version="1",
                    source_fields=("aces",),
                ),
            ),
        ),
    )

    return (
        set_registry,
        manifest,
        transform_registry,
        snapshot,
        lineage,
    )


def decision(tmp_path, lineage_override=None):
    (
        set_registry,
        manifest,
        transform_registry,
        snapshot,
        lineage,
    ) = setup(tmp_path)

    return evaluate_governed_feature_snapshot(
        snapshot=snapshot,
        base_snapshot_admission_fingerprint="e" * 64,
        feature_set_manifest_fingerprint=(
            manifest.manifest_fingerprint
        ),
        feature_set_manifest_registry=set_registry,
        lineage_entries=(
            lineage
            if lineage_override is None
            else lineage_override
        ),
        transformation_registry=transform_registry,
    )


def test_exact_lineage_admits_snapshot(tmp_path):
    value = decision(tmp_path)

    assert value.status == "ADMIT"
    assert value.downstream_eligible is True
    assert value.lineage_fingerprint is not None


def test_missing_lineage_quarantines_snapshot(tmp_path):
    value = decision(tmp_path, lineage_override=())

    assert value.status == "QUARANTINE"
    assert "MISSING_EXACT_FEATURE_LINEAGE" in value.reason_codes


def test_source_schema_version_and_fields_are_exact(tmp_path):
    (
        set_registry,
        manifest,
        transform_registry,
        snapshot,
        lineage,
    ) = setup(tmp_path)

    bad = (
        FeatureLineageEntry(
            feature_definition_fingerprint=(
                lineage[0].feature_definition_fingerprint
            ),
            transformation_fingerprint=(
                lineage[0].transformation_fingerprint
            ),
            sources=(
                FeatureLineageSource(
                    source_record_fingerprint="c" * 64,
                    schema_name="tennis.player.match_history",
                    schema_version="99",
                    source_fields=("aces",),
                ),
            ),
        ),
    )

    value = evaluate_governed_feature_snapshot(
        snapshot=snapshot,
        base_snapshot_admission_fingerprint="e" * 64,
        feature_set_manifest_fingerprint=(
            manifest.manifest_fingerprint
        ),
        feature_set_manifest_registry=set_registry,
        lineage_entries=bad,
        transformation_registry=transform_registry,
    )

    assert value.status == "QUARANTINE"
    assert any(
        reason.startswith(
            "UNDECLARED_TRANSFORMATION_SOURCE_SCHEMA:"
        )
        for reason in value.reason_codes
    )


def test_governed_admission_evidence_rederives_and_audits(tmp_path):
    value = decision(tmp_path)
    path = tmp_path / "admission.db"
    store = SQLiteGovernedFeatureAdmissionEvidence(path)

    first = store.record_decision(value)
    second = store.record_decision(value)

    assert first == second
    assert store.audit_integrity().ok is True

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE governed_feature_admission
            SET evidence_id = ?
            WHERE decision_fingerprint = ?
            """,
            ("f" * 64, value.decision_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity().ok is False
