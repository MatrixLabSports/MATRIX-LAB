"""Prevent two independent GitHub runners from editing the same Over25 reports."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / ".github/workflows/matrix-over25-independent-settlement.yml"
WINDOWS = ROOT / ".github/workflows/matrix-selfhosted-browser-quotes-5m.yml"
WINDOWS_PERSIST = ROOT / "tools/windows/persist_matrix_browser_evidence.ps1"
CLOUD_REPORTS = (
    "MATRIX_INDEPENDENT_OVER25_SETTLEMENT_LAST.json",
    "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json",
    "MATRIX_OVER25_RESEARCH_SOURCE_HASH_REPAIR_LAST.json",
    "MATRIX_OVER25_MISSING_SOURCE_EXACT_RESTORE_LAST.json",
)

def test_windows_only_stages_browser_owned_reports():
    script = WINDOWS_PERSIST.read_text(encoding="utf-8")
    allowlist = script.split("$allowed = @(", 1)[1].split(")", 1)[0]
    for name in CLOUD_REPORTS:
        assert name not in allowlist, "CLOUD_REPORT_STAGED_BY_WINDOWS:" + name
        assert ('git add -- "' + name + '"') not in script
    assert "MATRIX_BROWSER_CDP_COLLECTION_LAST.json" in script
    assert "MATRIX_SOFA_BROWSER_OBSERVATIONS.json" in allowlist

def test_only_cloud_performs_historical_settlement_and_sha_repair():
    cloud = CLOUD.read_text(encoding="utf-8")
    windows = WINDOWS.read_text(encoding="utf-8")
    assert "python -m tools.matrix_over25_settlement_due" in cloud
    assert "cron: '16 */2 * * *'" in cloud
    assert "FOOTBALL_DATA_ORG_TOKEN" in cloud
    assert "python -m tools.matrix_over25_settlement_due" not in windows
    assert "python -m tools.matrix_independent_over25_research_settlement" not in windows
    assert "python -m tools.matrix_over25_source_hash_exact_repair --restore-verifiable" not in windows
    assert "python -m tools.matrix_over25_missing_source_exact_restore --restore" not in windows
    for name in CLOUD_REPORTS:
        assert name in cloud
    assert "REAL_MONEY: BLOCKED" in windows and "REAL_MONEY: BLOCKED" in cloud
    assert "AUTO_BETTING: DISABLED" in windows and "AUTO_BETTING: DISABLED" in cloud

def test_no_automatic_text_conversion_of_sha_archives():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "evidence/football_research_freezes/** -text" in attributes


def test_windows_browser_publisher_isolated_worktree_preserves_unstaged_evidence():
    script = WINDOWS_PERSIST.read_text(encoding="utf-8")
    assert "git worktree add --detach $scratch $remoteCommit" in script
    assert "git -C $scratch cherry-pick $evidenceCommit" in script
    assert "git -C $scratch push origin HEAD:repair/cor09-world-pipeline" in script
    assert "BROWSER_EVIDENCE_PUBLISHED_FROM_ISOLATED_CLEAN_WORKTREE" in script
    assert "BROWSER_EVIDENCE_CHERRY_PICK_CONFLICT_FAIL_CLOSED" in script
    assert "git rebase origin/repair/cor09-world-pipeline" not in script
    for unsafe in ("git stash", "git reset --hard", "git clean -fd", "push --force"):
        assert unsafe not in script
    assert "REAL_MONEY" in script and "AUTO_BETTING" in script
