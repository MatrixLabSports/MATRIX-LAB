from pathlib import Path

WORKFLOW = Path(".github/workflows/cor0203-batch-freeze.yml")
CYCLE = Path("scripts/cor0203_production_cycle.sh")


def test_scheduler_heartbeat_does_not_self_retrigger_batch_writer():
    workflow = WORKFLOW.read_text(encoding="utf-8-sig")
    cycle = CYCLE.read_text(encoding="utf-8-sig")

    heartbeat_path = (
        "evidence/cor0203/runtime/"
        "MATRIX_COR0203_SCHEDULER_HEARTBEAT.json"
    )

    # The governed writer remains serialized.
    assert "concurrency:" in workflow
    assert "cancel-in-progress: false" in workflow

    # A heartbeat is evidence produced/persisted by the production cycle,
    # but it must not be a push-path trigger for the same writer.
    assert heartbeat_path not in workflow
    assert f'HEARTBEAT="{heartbeat_path}"' in cycle
    assert 'git add "$HEARTBEAT"' in cycle
