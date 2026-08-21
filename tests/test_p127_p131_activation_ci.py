from pathlib import Path


def test_p127_p131_canonical_ci_boundary_is_present():
    ci = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "_provider_network_activation_hardening_boundary"
        in ci
    )
    assert (
        "_provider_network_activation_hardening_boundary(ROOT)"
        in ci
    )

    for token in (
        "TLSVersion.TLSv1_2",
        "HTTP_RESPONSE_FRAMING_CONFLICT",
        "require_trusted_production_connector",
        "NONEMPTY_REQUEST_CONTRACT_EVIDENCE_REQUIRED",
        "REHEARSAL_CERTIFIED_FAIL_CLOSED",
    ):
        assert token in ci
