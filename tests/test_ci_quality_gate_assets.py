from pathlib import Path


def test_gate_implements_declared_policy_checks():
    source = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for required in (
        "compileall",
        "tracked_secret_scan",
        "git_diff_check",
        "sport_boundary",
        "safety_invariants",
    ):
        assert required in source

    assert "HEAD^" in source
    assert "PYTHON_VERSION_BELOW_POLICY" in source
    assert "SPORT_BOUNDARY_VIOLATION" in source


def test_workflow_remains_read_only():
    workflow = Path(
        ".github/workflows/matrix-ci.yml"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert (
        "python scripts/matrix_ci_gate.py"
        in workflow
    )
