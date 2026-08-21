
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_p132_p136_semantic_ci_boundary_is_wired():
    source = (
        ROOT
        / "scripts"
        / "matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "def _provider_response_ingest_boundary("
        in source
    )
    assert (
        "_provider_response_ingest_boundary(ROOT)"
        in source
    )


def test_p133_protocol_and_partial_ingestion_semantics_remain_bound():
    fixture = (
        ROOT
        / "app/providers/api_football/fixture_service.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    validation = (
        ROOT
        / "app/providers/api_football/response_validation.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        fixture.index(
            "request_and_validate_api_football_response("
        )
        < fixture.index(
            "adapt_api_football_fixture("
        )
    )

    assert (
        "API_FOOTBALL_RESPONSE_ITEM_NOT_MAPPING"
        in validation
    )
    assert (
        "P135 partial-ingestion semantics"
        in validation
    )


def test_p136_final_provenance_controls_are_semantically_bound():
    source = (
        ROOT
        / "app/providers/api_football/offline_ingest_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "request_parameter_values_fingerprint",
        "evidence_store.get_verified",
        "OFFLINE_INGEST_PAYLOAD_DATE_MISMATCH",
        "OFFLINE_INGEST_SHADOW_PARAMETER_VALUES_FINGERPRINT_MISMATCH",
        "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV",
        "require_authoritative_store",
        "_source_revision()",
    ):
        assert token in source

    tree = ast.parse(
        source
    )

    certifier = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "certify_api_football_offline_fixture_ingest"
    )

    parameter_names = {
        argument.arg
        for argument
        in (
            certifier.args.posonlyargs
            + certifier.args.args
            + certifier.args.kwonlyargs
        )
    }

    assert (
        "source_revision"
        not in parameter_names
    )

    assert {
        "shadow_evidence_store",
        "shadow_request_evidence_id",
        "evidence_store",
    }.issubset(
        parameter_names
    )
