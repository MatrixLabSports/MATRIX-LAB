"""Regression checks: each Team Total run must be archived and persisted."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_team_total_writes_archive_before_last_snapshot():
    source = (ROOT / "tools/telegram_team_total_goals_picks.py").read_text(encoding="utf-8")
    assert 'team_total_goals_run_history' in source
    assert 'archive_path.write_text(serialized_audit' in source
    assert 'Path(a.audit).write_text(serialized_audit' in source
    assert source.index('archive_path.write_text(serialized_audit') < source.index('Path(a.audit).write_text(serialized_audit')

def test_workflow_commits_run_history():
    workflow = (ROOT / ".github/workflows/telegram-team-total-goals-picks.yml").read_text(encoding="utf-8")
    assert "evidence/notifications/telegram/team_total_goals_run_history/" in workflow
    assert "git rebase origin/repair/cor09-world-pipeline" in workflow
