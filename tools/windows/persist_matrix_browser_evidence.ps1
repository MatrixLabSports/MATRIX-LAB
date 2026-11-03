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
  "evidence/notifications/telegram/MATRIX_BROWSER_CDP_COLLECTION_LAST.json"
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
if (Test-Path -LiteralPath "evidence/football_world_inventory") {
  Get-ChildItem "evidence/football_world_inventory" -Recurse -File -Filter "MATRIX_BETANO_QUOTE_*.json" |
    ForEach-Object {
      $rel = $_.FullName.Substring((Get-Location).Path.Length + 1)
      git add -- $rel
      if ($LASTEXITCODE -ne 0) { throw "BROWSER_GIT_ADD_FAILED" }
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
for ($attempt = 1; $attempt -le 4; $attempt++) {
  git fetch origin repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) { throw "BROWSER_EVIDENCE_FETCH_FAILED" }
  git rebase origin/repair/cor09-world-pipeline
  if ($LASTEXITCODE -ne 0) {
    git rebase --abort
    throw "BROWSER_EVIDENCE_REBASE_CONFLICT_FAIL_CLOSED"
  }
  git push origin HEAD:repair/cor09-world-pipeline
  if ($LASTEXITCODE -eq 0) {
    Write-Output "MATRIX_BROWSER_EVIDENCE_PUSHED"
    exit 0
  }
  Start-Sleep -Seconds (2 * $attempt)
}
throw "BROWSER_EVIDENCE_PUSH_FAILED"
