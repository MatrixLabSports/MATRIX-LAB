from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path

import pytest

from matrix_elite.support_contract_bindings import (
    BINDING_LAYER_VERSION,
    FAILOVER_REQUIRED_CONTROL_IDS,
    FAILOVER_VERSION_FIELD_BY_CONTROL,
    FailoverSupportContractVersions,
    LIVE_REQUIRED_CONTROL_IDS,
    LIVE_VERSION_FIELD_BY_CONTROL,
    LiveSupportContractVersions,
    PREDICTIVE_REQUIRED_CONTROL_IDS,
    PREDICTIVE_VERSION_FIELD_BY_CONTROL,
    PredictiveSupportContractVersions,
    REQUIRED_CONTROL_IDS,
    REQUIRED_EXACT_VERSION_FIELDS,
    SOURCE_HEAD,
    EvidenceRef,
    SupportContractBinding,
    binding_registry,
    exact_bundle_field_names,
    failover_versions,
    live_versions,
    predictive_versions,
    registry_payload,
    repository_evidence_audit,
    validate_binding_registry,
    version_field_bindings,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = (
    ROOT
    / "docs"
    / "elite_remediation"
    / "support_contract_bindings"
    / "MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_REGISTRY_R1.json"
)


def test_required_control_and_version_field_cardinality_is_exact() -> None:
    assert len(REQUIRED_CONTROL_IDS) == 21
    assert len(set(REQUIRED_CONTROL_IDS)) == 21
    assert len(REQUIRED_EXACT_VERSION_FIELDS) == 19
    assert len(set(REQUIRED_EXACT_VERSION_FIELDS)) == 19
    assert len(PREDICTIVE_REQUIRED_CONTROL_IDS) == 10
    assert len(LIVE_REQUIRED_CONTROL_IDS) == 5
    assert len(FAILOVER_REQUIRED_CONTROL_IDS) == 6


def test_exact_bundle_field_names_match_scope_governance_contracts() -> None:
    assert exact_bundle_field_names() == {
        "PREDICTIVE": tuple(PREDICTIVE_VERSION_FIELD_BY_CONTROL.values()),
        "LIVE": tuple(LIVE_VERSION_FIELD_BY_CONTROL.values()),
        "FAILOVER": tuple(FAILOVER_VERSION_FIELD_BY_CONTROL.values()),
    }
    assert tuple(field.name for field in fields(PredictiveSupportContractVersions)) == tuple(
        PREDICTIVE_VERSION_FIELD_BY_CONTROL.values()
    )
    assert tuple(field.name for field in fields(LiveSupportContractVersions)) == tuple(
        LIVE_VERSION_FIELD_BY_CONTROL.values()
    )
    assert tuple(field.name for field in fields(FailoverSupportContractVersions)) == tuple(
        FAILOVER_VERSION_FIELD_BY_CONTROL.values()
    )


def test_registry_is_immutable_non_promoting_and_non_template() -> None:
    rows = binding_registry()
    assert validate_binding_registry(rows) == ()
    assert all(row.support_declared is False for row in rows)
    assert all(row.support_status == "NOT_EVALUATED" for row in rows)
    assert all(
        row.semantic_review_status == "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT"
        for row in rows
    )
    assert all("<" not in row.binding_version and "|" not in row.binding_version for row in rows)
    assert all(row.binding_version.startswith(BINDING_LAYER_VERSION + "/") for row in rows)
    with pytest.raises(FrozenInstanceError):
        rows[0].control_id = "tampered"  # type: ignore[misc]


def test_version_bundles_are_derived_from_registry_not_hand_filled() -> None:
    field_map = version_field_bindings()
    predictive = predictive_versions()
    live = live_versions()
    failover = failover_versions()
    for name in PREDICTIVE_VERSION_FIELD_BY_CONTROL.values():
        assert getattr(predictive, name) == field_map[name]
    for name in LIVE_VERSION_FIELD_BY_CONTROL.values():
        assert getattr(live, name) == field_map[name]
    for name in FAILOVER_VERSION_FIELD_BY_CONTROL.values():
        assert getattr(failover, name) == field_map[name]


def test_static_registry_json_matches_python_canonical_payload() -> None:
    assert REGISTRY_PATH.is_file()
    on_disk = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert on_disk == registry_payload()
    assert on_disk["support_declared"] is False
    assert on_disk["supportability_pack_generated"] is False
    assert on_disk["candidate_inventory_generated"] is False
    assert on_disk["selection_r2_executed"] is False
    assert on_disk["performance_information_used"] is False


def test_candidate_evidence_refs_are_exact_and_present() -> None:
    audit = repository_evidence_audit(ROOT)
    assert audit["result"] == "PASS", json.dumps(audit, sort_keys=True)
    assert audit["checked_evidence_ref_count"] == 42
    assert audit["support_declared"] is False
    assert audit["supportability_pack_ready"] is False


def test_evidence_ref_rejects_unsafe_paths_and_bad_hashes() -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        EvidenceRef(path="C:/escape.py", sha256="a" * 64)
    with pytest.raises(ValueError, match="escape"):
        EvidenceRef(path="../escape.py", sha256="a" * 64)
    with pytest.raises(ValueError, match="64 lowercase hex"):
        EvidenceRef(path="safe.py", sha256="ABC")


def test_binding_layer_rejects_support_promotion() -> None:
    row = binding_registry()[0]
    with pytest.raises(ValueError, match="support may not be declared"):
        SupportContractBinding(
            control_id=row.control_id,
            scope_kind=row.scope_kind,
            binding_version=row.binding_version,
            required_identity_version_field=row.required_identity_version_field,
            implementation_evidence=row.implementation_evidence,
            test_evidence=row.test_evidence,
            source_head=SOURCE_HEAD,
            support_status="NOT_EVALUATED",
            support_declared=True,
            semantic_review_status="PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT",
        )


def test_every_control_has_distinct_binding_version_and_two_non_circular_evidence_refs() -> None:
    rows = binding_registry()
    assert len({row.binding_version for row in rows}) == 21
    for row in rows:
        assert not row.implementation_evidence.path.startswith("tools/elite_evidence/")
        assert not row.test_evidence.path.startswith("tools/elite_evidence/")
        assert "/scope_governance/" not in row.implementation_evidence.path
        assert "/scope_governance/" not in row.test_evidence.path
