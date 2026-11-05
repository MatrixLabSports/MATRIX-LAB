# MATRIX Windows PowerShell 5.1 read-only browser evidence persistence.
# Invoked explicitly via powershell.exe -ExecutionPolicy Bypass -File.
# Never stage browser profiles, credentials, tokens or live betting actions.
$ErrorActionPreference = "Stop"
if ($env:REAL_MONEY -ne "BLOCKED" -or $env:AUTO_BETTING -ne "DISABLED") {
  throw "MATRIX_BROWSER_PERSIST_SAFETY_GUARD"
}
git config user.name "matrix-browser-runner"
if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_CONFIG_FAILED" }
git config user.email "matrix-browser-runner@users.noreply.github.com"
if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_CONFIG_FAILED" }

$files = @(
  "evidence/notifications/telegram/MATRIX_SELF_HOSTED_BROWSER_HEALTH_LAST.json",
  "evidence/notifications/telegram/MATRIX_BROWSER_CDP_COLLECTION_LAST.json",
  "evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json"
)
foreach ($file in $files) {
  if (Test-Path -LiteralPath $file -PathType Leaf) {
    git add -- $file
    if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_ADD_FAILED" }
  }
}
if (Test-Path -LiteralPath "evidence/notifications/telegram/browser_cdp") {
  git add -- "evidence/notifications/telegram/browser_cdp"
  if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_ADD_FAILED" }
}
# Statistical postmatch reports are cloud-owned; Windows must never stage them.
# This prevents cross-workflow git rebase conflicts during the 5-minute cycle.
# Preserve only independently sourced browser calendar evidence and its guarded
# crosscheck. Never stage model predictions, canonical candidates or credentials.
if (Test-Path -LiteralPath "evidence/football_world_inventory") {
  $allowed = @("MATRIX_SOFA_BROWSER_OBSERVATIONS.json", "MATRIX_OPERA_CALENDAR_HANDOFF_RECEIPT_LAST.json", "MATRIX_FLASH_OPERA_LINK_ONLY_HANDOFF_LAST.json", "MATRIX_FLASH_INDIVIDUAL_DETAIL_VERIFICATION_LAST.json", "MATRIX_FLASH_SOFA_TWO_SOURCE_REPORT_LAST.json", "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json", "MATRIX_CHAMPIONSHIP_8_OF_11_IDENTITY_GAP_LAST.json", "MATRIX_SIX_LEAGUE_PROSPECTIVE_PREFLIGHT_LAST.json", "MATRIX_SIX_LEAGUE_EXISTING_EVIDENCE_RECOVERY_LAST.json", "MATRIX_ORIGINAL_CANONICAL_PROBABILITY_MANIFEST_AUDIT_LAST.json", "MATRIX_OVER25_NONCANONICAL_PROBABILITY_RECOVERY_LAST.json", "MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json", "MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json", "MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_CYCLE_LAST.json", "MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json", "MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_LAST.json")
  foreach ($name in $allowed) {
    Get-ChildItem "evidence/football_world_inventory" -Recurse -File -Filter $name |
      ForEach-Object {
        $rel = $_.FullName.Substring((Get-Location).Path.Length + 1)
        git add -- $rel
        if ($LASTEXITCODE -ne 0) { throw "CALENDAR_EVIDENCE_GIT_ADD_FAILED" }
      }
  }
}
# Only content-addressed, append-only independent research source/forecast files.
# No production, market candidates, credentials, or betting artifacts.
if (Test-Path -LiteralPath "evidence/football_research_freezes") {
  git add -- "evidence/football_research_freezes"
  if ($LASTEXITCODE -ne 0) { throw "INDEPENDENT_RESEARCH_FREEZE_GIT_ADD_FAILED" }
}
if (Test-Path -LiteralPath "evidence/football_world_inventory") {
  Get-ChildItem "evidence/football_world_inventory" -Recurse -File -Filter "MATRIX_BETANO_QUOTE_*.json" |
    ForEach-Object {
      $rel = $_.FullName.Substring((Get-Location).Path.Length + 1)
      git add -- $rel
      if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_ADD_FAILED" }
    }
}
if (Test-Path -LiteralPath "evidence/football_world_inventory") {
  Get-ChildItem "evidence/football_world_inventory" -Recurse -File -Filter "MATRIX_BETANO_RESEARCH_MARKET_*.json" |
    ForEach-Object {
      $rel = $_.FullName.Substring((Get-Location).Path.Length + 1)
      git add -- $rel
      if ($LASTEXITCODE -ne 0) { throw "RESEARCH_MARKET_EVIDENCE_ADD_FAILED" }
    }
}
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Output "MATRIX_BROWSER_NO_EVIDENCE_CHANGE"
  exit 0
}
if ($LASTEXITCODE -ne 1) { throw "BROWSER_GIT_DIFF_FAILED" }
git commit -m "evidence(browser): persist self-hosted quote collection cycle"
if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_COMMIT_FAILED" }
# Preserve the runner's working tree exactly as it is. Other verified research
# stages may leave unstaged reports that this browser-only publisher MUST NOT
# commit, stash, reset or discard. Rebase of this dirty worktree is unsafe.
# Replay ONLY the allowlisted evidence commit into a fresh temporary worktree.
$evidenceCommit = (git rev-parse --verify HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $evidenceCommit -notmatch '^[0-9a-f]{40}$') {
  throw "BROWSER_EVIDENCE_COMMIT_SHA_INVALID"
}
if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP) -or -not (Test-Path -LiteralPath $env:RUNNER_TEMP -PathType Container)) {
  throw "BROWSER_EVIDENCE_RUNNER_TEMP_MISSING"
}
for ($attempt = 1; $attempt -le 4; $attempt++) {
  git fetch origin repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) { throw "BROWSER_EVIDENCE_FETCH_FAILED" }
  $remoteCommit = (git rev-parse --verify origin/repair/cor09-world-pipeline).Trim()
  if ($LASTEXITCODE -ne 0 -or $remoteCommit -notmatch '^[0-9a-f]{40}$') {
    throw "BROWSER_EVIDENCE_REMOTE_SHA_INVALID"
  }
  $scratch = Join-Path $env:RUNNER_TEMP ("matrix-browser-publish-" + [Guid]::NewGuid().ToString("N"))
  $added = $false
  $replayConflict = $false
  $pushed = $false
  try {
    git worktree add --detach $scratch $remoteCommit
    if ($LASTEXITCODE -ne 0) { throw "BROWSER_EVIDENCE_CLEAN_WORKTREE_CREATE_FAILED" }
    $added = $true
    git -C $scratch cherry-pick $evidenceCommit
    if ($LASTEXITCODE -ne 0) {
      $replayConflict = $true
      # A real same-file conflict must remain fail-closed; never overwrite
      # the remote's newer data and never fake a successful publication.
      git -C $scratch status --short
      throw "BROWSER_EVIDENCE_CHERRY_PICK_CONFLICT_FAIL_CLOSED"
    }
    git -C $scratch push origin HEAD:repair/cor09-world-pipeline
    $pushed = ($LASTEXITCODE -eq 0)
  }
  finally {
    if ($added) {
      if ($replayConflict) {
        git -C $scratch cherry-pick --abort
        if ($LASTEXITCODE -ne 0) {
          Write-Warning "BROWSER_EVIDENCE_SCRATCH_CONFLICT_RETAINED: $scratch"
          throw "BROWSER_EVIDENCE_SCRATCH_ABORT_FAILED"
        }
      }
      git worktree remove $scratch
      if ($LASTEXITCODE -ne 0) {
        Write-Warning "BROWSER_EVIDENCE_SCRATCH_RETAINED: $scratch"
        throw "BROWSER_EVIDENCE_SCRATCH_REMOVE_FAILED"
      }
    }
  }
  if ($pushed) {
    Write-Output "MATRIX_BROWSER_EVIDENCE_PUSHED"
    Write-Output "BROWSER_EVIDENCE_PUBLISHED_FROM_ISOLATED_CLEAN_WORKTREE"
    exit 0
  }
  # Only a remote non-fast-forward race is retried; an actual conflict throws.
  Start-Sleep -Seconds (2 * $attempt)
}
throw "BROWSER_EVIDENCE_PUSH_FAILED"
