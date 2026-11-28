"""Protect the five-minute Windows publisher from unbounded archive rescans.

These tests inspect production PowerShell source, while the Windows GitHub
workflow performs an isolated real git worktree/push integration test.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLISH=ROOT/"tools"/"windows"/"persist_matrix_browser_evidence.ps1"


def test_only_two_prospective_bogota_days_are_scanned():
    s=PUBLISH.read_text(encoding="utf-8")
    assert '"SA Pacific Standard Time"' in s
    assert '$activeDays = @(' in s
    assert '$bogotaNow.AddDays(1)' in s
    assert 'foreach ($day in $activeDays)' in s
    assert 'Get-ChildItem "evidence/football_world_inventory" -Recurse' not in s
    assert 'git add -- "evidence/football_research_freezes"' not in s
    assert '$freezes = "evidence/football_research_freezes/$day"' in s


def test_preserve_authenticated_browser_and_forensics_without_promoting_probabilities():
    s=PUBLISH.read_text(encoding="utf-8")
    assert 'MATRIX_SOFA_BROWSER_OBSERVATIONS.json' in s
    assert 'MATRIX_FLASH_INDIVIDUAL_DETAIL_VERIFICATION_LAST.json' in s
    assert 'MATRIX_BETANO_QUOTE_*.json' in s
    assert 'MATRIX_BETANO_RESEARCH_MARKET_*.json' in s
    assert 'MATRIX_BROWSER_CDP_COLLECTION_LAST.json' in s
    assert 'MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json' in s
    assert 'MATRIX_CHAMPIONSHIP_8_OF_11_IDENTITY_GAP_LAST.json' in s
    assert '2026-11-03' in s
    assert 'git worktree add --detach $scratch $remoteCommit' in s
    assert 'BROWSER_EVIDENCE_CHERRY_PICK_CONFLICT_FAIL_CLOSED' in s
    assert 'git -C $scratch push origin HEAD:repair/cor09-world-pipeline' in s
    assert 'BROWSER_EVIDENCE_PUBLISHED_FROM_ISOLATED_CLEAN_WORKTREE' in s
    assert 'REAL_MONEY' in s and 'AUTO_BETTING' in s
    for disallowed in ('git reset --hard','git stash','git clean -fd','push --force'):
        assert disallowed not in s


def test_independent_settlement_files_remain_cloud_owned():
    s=PUBLISH.read_text(encoding="utf-8")
    for name in (
        'MATRIX_INDEPENDENT_OVER25_SETTLEMENT_LAST.json',
        'MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json',
        'MATRIX_OVER25_RESEARCH_SOURCE_HASH_REPAIR_LAST.json',
        'MATRIX_OVER25_MISSING_SOURCE_EXACT_RESTORE_LAST.json',
    ):
        assert name not in s
    assert 'evidence/api_football/daily_prematch_reports' not in s
    assert 'TELEGRAM_BOT_TOKEN' not in s
    assert 'ODDS_API_NET_KEY' not in s
