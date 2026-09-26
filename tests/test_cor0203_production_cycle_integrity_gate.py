from pathlib import Path

CYCLE = Path("scripts/cor0203_production_cycle.sh")
WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")


def test_integrity_audit_runs_after_batch_runner_before_persistence():
    text = CYCLE.read_text(encoding="utf-8-sig")
    runner = text.index("python -m tools.cor0203_batch_runner")
    audit = text.index("python -m tools.cor0203_holdout_integrity_audit")
    git_add = text.index('git add "$INTEGRITY_LAST"')
    assert runner < audit < git_add


def test_cycle_fail_closes_on_holdout_integrity():
    text = CYCLE.read_text(encoding="utf-8-sig")
    assert 'assert integrity["result"] == "PASS"' in text
    assert 'assert integrity["failed_observations"] == 0' in text
    assert 'assert integrity["median_or_neutral_fallback_admissible"] is False' in text
    assert 'assert integrity["admissible_observations"] == runner["ending_physical_count"]' in text


def test_integrity_tool_is_a_workflow_trigger():
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    assert "tools/cor0203_holdout_integrity_audit.py" in text
