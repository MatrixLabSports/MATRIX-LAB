# Windows PowerShell 5.1 — persist only browser-visible tennis research evidence.
$ErrorActionPreference = "Stop"
if ($env:REAL_MONEY -ne "BLOCKED" -or $env:AUTO_BETTING -ne "DISABLED") { throw "TENNIS_BROWSER_SAFETY_GUARD" }
git config user.name "matrix-tennis-browser-runner"
if ($LASTEXITCODE -ne 0) { throw "GIT_CONFIG_FAILED" }
git config user.email "matrix-tennis-browser-runner@users.noreply.github.com"
if ($LASTEXITCODE -ne 0) { throw "GIT_CONFIG_FAILED" }
$folders = @("evidence/tennis_calendar_physical", "evidence/tennis_calendar_reconciliation")
foreach ($folder in $folders) {
  if (Test-Path -LiteralPath $folder) {
    git add -- $folder
    if ($LASTEXITCODE -ne 0) { throw "TENNIS_RESEARCH_GIT_ADD_FAILED" }
  }
}
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Output "TENNIS_BROWSER_NO_EVIDENCE_CHANGE"; exit 0 }
if ($LASTEXITCODE -ne 1) { throw "TENNIS_BROWSER_DIFF_FAILED" }
git commit -m "evidence(tennis): new authentic browser-first world date capture"
if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_COMMIT_FAILED" }
for ($attempt=1; $attempt -le 5; $attempt++) {
  git fetch origin repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) { throw "TENNIS_BROWSER_FETCH_FAILED" }
  git rebase origin/repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) { git rebase --abort; throw "TENNIS_BROWSER_REBASE_CONFLICT_FAIL_CLOSED" }
  git push origin HEAD:repair/cor09-world-pipeline
  if ($LASTEXITCODE -eq 0) { Write-Output "TENNIS_BROWSER_AUTHENTIC_EVIDENCE_PERSISTED"; exit 0 }
  Start-Sleep -Seconds (2*$attempt)
}
throw "TENNIS_BROWSER_PERSIST_EXHAUSTED"
