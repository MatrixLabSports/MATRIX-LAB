from pathlib import Path


def test_ci_workflow_and_gate_exist():
    gate = Path(
        "scripts/matrix_ci_gate.py"
    )
    workflow_path = Path(
        ".github/workflows/matrix-ci.yml"
    )

    assert gate.is_file()
    assert workflow_path.is_file()

    source = gate.read_text(
        encoding="utf-8-sig"
    )
    workflow = workflow_path.read_text(
        encoding="utf-8-sig"
    )

    assert (
        "sys.path.insert"
        in source
    )
    assert (
        "Path(__file__).resolve().parents[1]"
        in source
    )
    assert (
        "python scripts/matrix_ci_gate.py"
        in workflow
    )
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert "pull_request:" in workflow
