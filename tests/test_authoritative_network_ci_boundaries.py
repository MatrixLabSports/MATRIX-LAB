from pathlib import Path


def test_authoritative_runtime_admission_and_network_boundaries_are_enforced():
    source = Path("scripts/matrix_ci_gate.py").read_text(encoding="utf-8-sig")
    assert "AUTHORITATIVE_RUNTIME_ADMISSION_BOUNDARY_VIOLATION" in source
    assert "BASE_RUNTIME_ADMISSION_IMPORT" in source
    assert "REQUESTS_IMPORT_IN_GOVERNED_BOUNDARY" in source
    assert "DIRECT_GOVERNED_HTTP_SESSION_IMPORT" in source
    assert "UNAUTHORIZED_REQUESTS_SESSION" in source
