
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _safety_literal_bindings(source: str):
    targets = {
        "real_provider_execution_authorized",
        "automatic_provider_switch",
        "automatic_wagering",
    }

    false_counts = {target: 0 for target in targets}
    true_bindings = []

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in targets
                ):
                    continue

                if isinstance(value, ast.Constant) and value.value is False:
                    false_counts[key.value] += 1
                elif isinstance(value, ast.Constant) and value.value is True:
                    true_bindings.append((key.value, node.lineno, "DICT"))

        elif isinstance(node, ast.keyword):
            if node.arg not in targets:
                continue

            if isinstance(node.value, ast.Constant) and node.value.value is False:
                false_counts[node.arg] += 1
            elif isinstance(node.value, ast.Constant) and node.value.value is True:
                true_bindings.append((node.arg, node.lineno, "KEYWORD"))

        elif isinstance(node, ast.Assign):
            if not isinstance(node.value, ast.Constant):
                continue

            for target in node.targets:
                name = None

                if isinstance(target, ast.Name):
                    name = target.id
                elif isinstance(target, ast.Attribute):
                    name = target.attr

                if name not in targets:
                    continue

                if node.value.value is False:
                    false_counts[name] += 1
                elif node.value.value is True:
                    true_bindings.append((name, node.lineno, "ASSIGN"))

    return false_counts, tuple(true_bindings)


def test_p132_p136_semantic_ci_boundary_is_wired():
    source = (
        ROOT / "scripts" / "matrix_ci_gate.py"
    ).read_text(encoding="utf-8-sig")

    assert "def _provider_response_ingest_boundary(" in source
    assert "_provider_response_ingest_boundary(ROOT)" in source


def test_p133_protocol_and_item_schema_precede_mapping():
    fixture = (
        ROOT / "app/providers/api_football/fixture_service.py"
    ).read_text(encoding="utf-8-sig")

    validation = (
        ROOT / "app/providers/api_football/response_validation.py"
    ).read_text(encoding="utf-8-sig")

    transport = (
        ROOT / "app/core/pinned_https_transport.py"
    ).read_text(encoding="utf-8-sig")

    assert (
        fixture.index("request_and_validate_api_football_response(")
        < fixture.index("adapt_api_football_fixture(")
    )

    assert "API_FOOTBALL_RESPONSE_ITEM_NOT_MAPPING" in validation
    assert '"SCHEMA"' in validation
    assert "class PinnedHttpProtocolError" in transport
    assert "strict_protocol=True" in transport


def test_p136_is_durable_attested_and_contract_bound():
    source = (
        ROOT / "app/providers/api_football/offline_ingest_certification.py"
    ).read_text(encoding="utf-8-sig")

    for required in (
        "SQLiteApiFootballOfflineIngestEvidenceStore",
        "hmac.compare_digest",
        "verify_provider_shadow_rehearsal_attestation",
        "shadow_request_evidence_id",
        "request_contract_id",
        "endpoint_manifest_id",
        "authorization_fingerprint",
        "code_fingerprint",
        "source_revision",
        "zero_network_topology_verified",
    ):
        assert required in source

    assert "network_call_count" not in source

    false_counts, true_bindings = _safety_literal_bindings(source)

    assert true_bindings == ()

    for target in (
        "real_provider_execution_authorized",
        "automatic_provider_switch",
        "automatic_wagering",
    ):
        assert false_counts[target] >= 1, target
