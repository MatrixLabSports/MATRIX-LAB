# Read-only SofaScore calendar preflight. Never edits OS execution policy or models.
$ErrorActionPreference = "Stop"
if ($env:REAL_MONEY -ne "BLOCKED" -or $env:AUTO_BETTING -ne "DISABLED") {
  throw "CALENDAR_SAFETY_GUARD"
}
$bogota = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
  [DateTime]::UtcNow, "SA Pacific Standard Time"
)
foreach ($day in @($bogota.ToString("yyyy-MM-dd"), $bogota.AddDays(1).ToString("yyyy-MM-dd"))) {
  $folder = "evidence/football_world_inventory/$day"
  $intake = "$folder/MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"
  $observed = "$folder/MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
  if (-not (Test-Path -LiteralPath $intake -PathType Leaf)) {
    Write-Output "CALENDAR_PROVIDER_INTAKE_MISSING:$day"
    continue
  }
  python -m tools.matrix_calendar_browser_observations --intake $intake --out $observed
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "CALENDAR_CAPTURE_FAILED_CLOSED:$day"
    continue
  }
  if (Test-Path -LiteralPath $observed -PathType Leaf) {
    python -m tools.matrix_football_sofa_fixture_crosscheck --intake $intake --observations $observed --out "$folder/MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json"
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "CALENDAR_SOFA_CROSSCHECK_FAILED_CLOSED:$day"
    }
  }
}
Write-Output "CALENDAR_PREMATCH_READONLY_COMPLETE_NO_TELEGRAM_AUTHORIZATION"
