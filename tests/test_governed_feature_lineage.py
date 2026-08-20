from types import SimpleNamespace

from app.core.feature_set_manifest_registry import (
    SQLiteFeatureSetManifestRegistry,
)
from app.core.feature_transformation_registry import (
    SQLiteFeatureTransformationRegistry,
    TransformationInput,
)
from app.core.governed_feature_lineage import (
    FeatureLineageEntry,
    SQLiteGovernedFeatureAdmissionEvidence,
    evaluate_governed_feature_snapshot,
)


def setup(tmp_path):
    feature_fp = "a" * 64

    set_registry = (
        SQLiteFeatureSetManifestRegistry(
            tmp_path / "sets.db"
        )
    )
    manifest = (
        set_registry.build_manifest(
            sport="tennis",
            entity_type="player",
            feature_set_key="prematch.core",
            feature_set_version="1",
            feature_definition_fingerprints=(
                feature_fp,
            ),
        )
    )
    set_registry.register(manifest)

    transform_registry = (
        SQLiteFeatureTransformationRegistry(
            tmp_path / "transforms.db"
        )
    )
    transformation = (
        transform_registry.build_transformation(
            sport="tennis",
            entity_type="player",
            transformation_key="serve.form",
            transformation_version="1",
            artifact_sha256="b" * 64,
            output_feature_definition_fingerprints=(
                feature_fp,
            ),
            inputs=(
                TransformationInput(
                    schema_name=(
                        "tennis.player.match_history"
                    ),
                    schema_version="1",
                    fields=("aces",),
                ),
            ),
        )
    )
    transform_registry.register(
        transformation
    )

    snapshot = SimpleNamespace(
        sport="tennis",
        canonical_id="tennis:player:subject",
        feature_set_key="prematch.core",
        feature_set_version="1",
        definition_fingerprints=(
            feature_fp,
        ),
        source_record_fingerprints=(
            "c" * 64,
        ),
        snapshot_fingerprint="d" * 64,
    )

    lineage = (
        FeatureLineageEntry(
            feature_definition_fingerprint=(
                feature_fp
            ),
            transformation_fingerprint=(
                transformation
                .transformation_fingerprint
            ),
            source_record_fingerprints=(
                "c" * 64,
            ),
            source_fields=("aces",),
        ),
    )

    return (
        manifest,
        transform_registry,
        snapshot,
        lineage,
    )


def test_exact_lineage_admits_snapshot(
    tmp_path,
):
    (
        manifest,
        transform_registry,
        snapshot,
        lineage,
    ) = setup(tmp_path)

    decision = (
        evaluate_governed_feature_snapshot(
            snapshot=snapshot,
            feature_set_manifest=manifest,
            lineage_entries=lineage,
            transformation_registry=(
                transform_registry
            ),
        )
    )

    assert decision.status == "ADMIT"
    assert (
        decision.downstream_eligible
        is True
    )
    assert (
        decision.lineage_fingerprint
        is not None
    )


def test_missing_lineage_quarantines_snapshot(
    tmp_path,
):
    (
        manifest,
        transform_registry,
        snapshot,
        _,
    ) = setup(tmp_path)

    decision = (
        evaluate_governed_feature_snapshot(
            snapshot=snapshot,
            feature_set_manifest=manifest,
            lineage_entries=(),
            transformation_registry=(
                transform_registry
            ),
        )
    )

    assert decision.status == "QUARANTINE"
    assert (
        "MISSING_EXACT_FEATURE_LINEAGE"
        in decision.reason_codes
    )


def test_undeclared_source_field_quarantines(
    tmp_path,
):
    (
        manifest,
        transform_registry,
        snapshot,
        lineage,
    ) = setup(tmp_path)

    bad = (
        FeatureLineageEntry(
            feature_definition_fingerprint=(
                lineage[0]
                .feature_definition_fingerprint
            ),
            transformation_fingerprint=(
                lineage[0]
                .transformation_fingerprint
            ),
            source_record_fingerprints=(
                "c" * 64,
            ),
            source_fields=("double_faults",),
        ),
    )

    decision = (
        evaluate_governed_feature_snapshot(
            snapshot=snapshot,
            feature_set_manifest=manifest,
            lineage_entries=bad,
            transformation_registry=(
                transform_registry
            ),
        )
    )

    assert decision.status == "QUARANTINE"
    assert any(
        reason.startswith(
            "UNDECLARED_TRANSFORMATION_FIELD:"
        )
        for reason
        in decision.reason_codes
    )


def test_governed_admission_evidence_is_idempotent(
    tmp_path,
):
    (
        manifest,
        transform_registry,
        snapshot,
        lineage,
    ) = setup(tmp_path)

    decision = (
        evaluate_governed_feature_snapshot(
            snapshot=snapshot,
            feature_set_manifest=manifest,
            lineage_entries=lineage,
            transformation_registry=(
                transform_registry
            ),
        )
    )

    store = (
        SQLiteGovernedFeatureAdmissionEvidence(
            tmp_path / "admission.db"
        )
    )

    first = store.record_decision(
        decision
    )
    second = store.record_decision(
        decision
    )

    assert first == second
