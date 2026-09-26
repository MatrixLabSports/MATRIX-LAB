from pathlib import Path

WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8-sig")


def test_cor0203_batch_workflow_is_serialized():
    text = _workflow_text()
    assert "concurrency:" in text
    assert "group: cor0203-holdout-repair-cor09-world-pipeline" in text
    assert "cancel-in-progress: false" in text


def test_cor0203_batch_workflow_pins_exact_trigger_sha():
    text = _workflow_text()
    assert "name: Checkout exact trigger state" in text
    assert "ref: ${{ github.sha }}" in text
    assert 'test "$CHECKOUT_SHA" = "$GITHUB_SHA"' in text
    assert "--trigger-sha \"$CHECKOUT_SHA\"" in text


def test_cor0203_batch_workflow_rebases_before_push():
    text = _workflow_text()
    assert "git fetch origin repair/cor09-world-pipeline" in text
    assert "git rebase origin/repair/cor09-world-pipeline" in text
