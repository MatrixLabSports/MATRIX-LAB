# MATRIX Windows PowerShell 5.1 — append-only, browser-visible tennis research.
# Publish from an isolated clean worktree; never rebase a dirty runner checkout.
# No paid API requests, predictions, quotas, odds, Telegram, or model mutations.
$ErrorActionPreference = "Stop"
if ($env:REAL_MONEY -ne "BLOCKED" -or $env:AUTO_BETTING -ne "DISABLED") {
  throw "TENNIS_BROWSER_SAFETY_GUARD"
}
git config user.name "matrix-tennis-browser-runner"
if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_GIT_CONFIG_FAILED" }
git config user.email "matrix-tennis-browser-runner@users.noreply.github.com"
if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_GIT_CONFIG_FAILED" }

$folders = @("evidence/tennis_calendar_physical", "evidence/tennis_calendar_reconciliation")
foreach ($folder in $folders) {
  if (Test-Path -LiteralPath $folder) {
    git add -- $folder
    if ($LASTEXITCODE -ne 0) { throw "TENNIS_RESEARCH_GIT_ADD_FAILED" }
  }
}
$staged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_STAGE_INSPECTION_FAILED" }
foreach ($name in $staged) {
  $normalized = $name.Replace([char]92, [char]47)
  if ($normalized -notmatch '^evidence/tennis_calendar_(physical|reconciliation)/[A-Za-z0-9_./-]+[.]json$') {
    throw "TENNIS_BROWSER_UNAUTHORIZED_STAGED_PATH"
  }
}
if ($staged.Count -eq 0) {
  Write-Output "TENNIS_BROWSER_NO_EVIDENCE_CHANGE"
  exit 0
}
git commit -m "evidence(tennis): append real free browser calendar observations"
if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_LOCAL_COMMIT_FAILED" }
$evidenceCommit = (git rev-parse --verify HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $evidenceCommit -notmatch '^[0-9a-f]{40}$') {
  throw "TENNIS_BROWSER_COMMIT_SHA_INVALID"
}
if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP) -or
  -not (Test-Path -LiteralPath $env:RUNNER_TEMP -PathType Container)) {
  throw "TENNIS_BROWSER_RUNNER_TEMP_MISSING"
}
for ($attempt = 1; $attempt -le 4; $attempt++) {
  git fetch origin repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_FETCH_FAILED" }
  $remoteCommit = (git rev-parse --verify origin/repair/cor09-world-pipeline).Trim()
  if ($LASTEXITCODE -ne 0 -or $remoteCommit -notmatch '^[0-9a-f]{40}$') {
    throw "TENNIS_BROWSER_REMOTE_SHA_INVALID"
  }
  $scratch = Join-Path $env:RUNNER_TEMP ("matrix-tennis-publish-" + [Guid]::NewGuid().ToString("N"))
  $added = $false
  $replayConflict = $false
  $pushed = $false
  try {
    git worktree add --detach $scratch $remoteCommit
    if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_CLEAN_WORKTREE_CREATE_FAILED" }
    $added = $true
    git -C $scratch cherry-pick $evidenceCommit
    if ($LASTEXITCODE -ne 0) {
      $replayConflict = $true
      git -C $scratch status --short
      throw "TENNIS_BROWSER_REAL_REMOTE_EVIDENCE_CONFLICT_FAIL_CLOSED"
    }
    git -C $scratch push origin HEAD:repair/cor09-world-pipeline
    $pushed = ($LASTEXITCODE -eq 0)
  }
  finally {
    if ($added) {
      if ($replayConflict) {
        git -C $scratch cherry-pick --abort
        if ($LASTEXITCODE -ne 0) {
          Write-Warning "TENNIS_BROWSER_SCRATCH_RETAINED: $scratch"
          throw "TENNIS_BROWSER_SCRATCH_ABORT_FAILED"
        }
      }
      git worktree remove $scratch
      if ($LASTEXITCODE -ne 0) {
        Write-Warning "TENNIS_BROWSER_SCRATCH_RETAINED: $scratch"
        throw "TENNIS_BROWSER_SCRATCH_REMOVE_FAILED"
      }
    }
  }
  if ($pushed) {
    Write-Output "TENNIS_BROWSER_AUTHENTIC_EVIDENCE_PERSISTED"
    Write-Output "TENNIS_BROWSER_PUBLISHED_FROM_ISOLATED_CLEAN_WORKTREE"
    exit 0
  }
  Start-Sleep -Seconds (2*$attempt)
}
throw "TENNIS_BROWSER_PERSIST_FAILED"
