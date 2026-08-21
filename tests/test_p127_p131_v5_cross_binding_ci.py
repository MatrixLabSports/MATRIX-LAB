import ast
from pathlib import Path


def test_p131_real_attempt_cross_binding_is_canonical_ci_boundary():
    ci = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    rehearsal = Path(
        "app/core/provider_activation_rehearsal.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    shadow = Path(
        "app/core/provider_shadow_rehearsal_evidence.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "def _provider_p131_real_attempt_cross_binding_boundary("
        in ci
    )
    assert (
        "_provider_p131_real_attempt_cross_binding_boundary(ROOT)"
        in ci
    )

    for token in (
        "network_permit_store",
        "contract_endpoint_binding_store",
        "SQLiteProviderNetworkPermitStore",
        "SQLiteProviderContractEndpointBindingStore",
        "contract_endpoint_binding_store.authorize",
        "NETWORK_CALL_STARTED",
        "INTERRUPTION_REAL_NETWORK_ATTEMPT_CROSS_BINDING_REQUIRED",
    ):
        assert token in rehearsal

    rehearsal_tree = ast.parse(
        rehearsal
    )
    permit_consumed_at_get = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "permit"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "consumed_at"
        for node in ast.walk(
            rehearsal_tree
        )
    )
    assert permit_consumed_at_get is True

    for token in (
        "build_provider_shadow_attestation_key_reference",
        "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY",
        "resolve_secret_runtime",
        "hmac.compare_digest",
    ):
        assert token in shadow

    assert (
        "real_provider_execution_authorized=True"
        not in rehearsal
    )
