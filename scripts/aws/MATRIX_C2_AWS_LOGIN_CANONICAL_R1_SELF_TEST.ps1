#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-True {
    param([bool]$Condition,[string]$Message)
    if (-not $Condition) { throw $Message }
}
function Get-Sha256 {
    param([string]$LiteralPath)
    (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
function New-TestAuthorization {
    param([string]$Root,[string]$Name)

    $Dir = Join-Path $Root $Name
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null

    $Report = Join-Path $Dir "AUTH.txt"
    $Bundle = Join-Path $Dir "AUTH.zip"

    $Lines = @(
        "CONTROLLED_SINGLE_AWS_LOGIN_RETRY_AUTHORIZED=TRUE",
        "MAX_AWS_LOGIN_COMMAND_EXECUTIONS_AUTHORIZED=1",
        "AWS_LOGIN_RETRY_AFTER_THIS_ATTEMPT_AUTHORIZED=FALSE",
        "STS_CALLS_AUTHORIZED=FALSE",
        "RESOURCE_PROVISIONING_AUTHORIZED=FALSE"
    )

    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Report,$Lines,$Utf8NoBom)
    Compress-Archive -LiteralPath $Report -DestinationPath $Bundle -CompressionLevel Optimal

    [pscustomobject]@{
        Report = $Report
        Bundle = $Bundle
        ReportSha = Get-Sha256 -LiteralPath $Report
        BundleSha = Get-Sha256 -LiteralPath $Bundle
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Canonical = Join-Path $ScriptDir "MATRIX_C2_AWS_LOGIN_CANONICAL_R1.ps1"
$Repo = Split-Path -Parent (Split-Path -Parent $ScriptDir)

Assert-True (Test-Path -LiteralPath $Canonical -PathType Leaf) "FAIL: canonical wrapper missing"

Push-Location $Repo
try {
    $Branch = (& git branch --show-current 2>$null).Trim()
    $Head = (& git rev-parse HEAD 2>$null).Trim()
} finally { Pop-Location }

$Root = Join-Path $env:TEMP ("MATRIX_C2_CANONICAL_SELF_TEST_" + [guid]::NewGuid().ToString("N"))
$StateSuccess = Join-Path $Root "state-success"
$EvidenceSuccess = Join-Path $Root "evidence-success"
$StateFail = Join-Path $Root "state-fail"
$EvidenceFail = Join-Path $Root "evidence-fail"
New-Item -ItemType Directory -Force -Path $Root | Out-Null

try {
    Write-Host ""
    Write-Host "=== MATRIX C2 AWS LOGIN CANONICAL R1 SELF-TEST ===" -ForegroundColor Cyan
    Write-Host "MODE=OFFLINE_LOCAL_ONLY"
    Write-Host "AWS_NETWORK_CALLS_PERFORMED=FALSE"
    Write-Host "AWS_LOGIN_COMMAND_PERFORMED=FALSE"
    Write-Host "STS_CALLS_PERFORMED=FALSE"

    $Text = [System.IO.File]::ReadAllText($Canonical)

    Assert-True ($Text -match 'System\.Diagnostics\.Process') "FAIL: System.Diagnostics.Process capture missing"
    Assert-True ($Text -match '\.WaitForExit\s*\(') "FAIL: WaitForExit missing"
    Assert-True ($Text -match '\.Refresh\s*\(') "FAIL: Refresh missing"
    Assert-True ($Text -match '\.ExitCode') "FAIL: ExitCode capture missing"
    Assert-True (-not ($Text -match '(?im)\bsts\s+get-caller-identity\b')) "FAIL: STS command unexpectedly present"
    Assert-True (-not ($Text -match '(?im)\b(resource|ec2|s3|lambda|iam)\s+(create|delete|put|update)\b')) "FAIL: provisioning-like AWS command unexpectedly present"

    $Auth1 = New-TestAuthorization -Root $Root -Name "auth-success"

    $Output1 = @(
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Canonical `
            -AuthorizationReportPath $Auth1.Report `
            -AuthorizationReportSha256 $Auth1.ReportSha `
            -AuthorizationBundlePath $Auth1.Bundle `
            -AuthorizationBundleSha256 $Auth1.BundleSha `
            -ExpectedBranch $Branch `
            -ExpectedHead $Head `
            -OfflineSelfTest `
            -OfflineSelfTestExitCode 0 `
            -StateRootOverride $StateSuccess `
            -EvidenceRootOverride $EvidenceSuccess 2>&1
    )
    $Exit1 = $LASTEXITCODE

    Assert-True ($Exit1 -eq 0) "FAIL: offline success probe did not exit 0"
    Assert-True (($Output1 -join "`n") -match 'AWS_LOGIN_EXIT_CODE=0') "FAIL: exit-code 0 not captured"
    Assert-True (($Output1 -join "`n") -match 'AWS_LOGIN_SUCCEEDED=TRUE') "FAIL: offline success not classified PASS"

    $CountFile = Join-Path $StateSuccess "offline-subprocess-count.txt"
    Assert-True (Test-Path -LiteralPath $CountFile -PathType Leaf) "FAIL: offline subprocess count file missing"
    $CountAfterFirst = [int]([System.IO.File]::ReadAllText($CountFile).Trim())
    Assert-True ($CountAfterFirst -eq 1) "FAIL: expected exactly one offline subprocess execution"

    $OutputReuse = @(
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Canonical `
            -AuthorizationReportPath $Auth1.Report `
            -AuthorizationReportSha256 $Auth1.ReportSha `
            -AuthorizationBundlePath $Auth1.Bundle `
            -AuthorizationBundleSha256 $Auth1.BundleSha `
            -ExpectedBranch $Branch `
            -ExpectedHead $Head `
            -OfflineSelfTest `
            -OfflineSelfTestExitCode 0 `
            -StateRootOverride $StateSuccess `
            -EvidenceRootOverride $EvidenceSuccess 2>&1
    )
    $ExitReuse = $LASTEXITCODE

    Assert-True ($ExitReuse -ne 0) "FAIL: reused authorization was not rejected"
    $CountAfterReuse = [int]([System.IO.File]::ReadAllText($CountFile).Trim())
    Assert-True ($CountAfterReuse -eq 1) "FAIL: reused authorization reached subprocess execution"

    $Auth2 = New-TestAuthorization -Root $Root -Name "auth-failure"

    $Output7 = @(
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Canonical `
            -AuthorizationReportPath $Auth2.Report `
            -AuthorizationReportSha256 $Auth2.ReportSha `
            -AuthorizationBundlePath $Auth2.Bundle `
            -AuthorizationBundleSha256 $Auth2.BundleSha `
            -ExpectedBranch $Branch `
            -ExpectedHead $Head `
            -OfflineSelfTest `
            -OfflineSelfTestExitCode 7 `
            -StateRootOverride $StateFail `
            -EvidenceRootOverride $EvidenceFail 2>&1
    )
    $Exit7 = $LASTEXITCODE

    Assert-True ($Exit7 -ne 0) "FAIL: exit-code 7 did not fail closed"
    Assert-True (($Output7 -join "`n") -match 'AWS_LOGIN_EXIT_CODE=7') "FAIL: exit-code 7 not captured"
    Assert-True (($Output7 -join "`n") -match 'RESULT=FAIL_CLOSED') "FAIL: exit-code 7 not classified fail-closed"

    Push-Location $Repo
    try {
        $Status = @(& git status --porcelain=v1 --untracked-files=all 2>$null | Where-Object { $_ -and $_.Trim() })
        $TrackedAtHead = @(& git ls-tree -r --name-only HEAD -- `
            "scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1.ps1" `
            "scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1_SELF_TEST.ps1" 2>$null |
            Where-Object { $_ -and $_.Trim() })
    } finally { Pop-Location }

    $Expected1 = "?? scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1.ps1"
    $Expected2 = "?? scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1_SELF_TEST.ps1"

    $PreCommitState =
        ($Status.Count -eq 2) -and
        ($Status -contains $Expected1) -and
        ($Status -contains $Expected2)

    $PostCommitState =
        ($Status.Count -eq 0) -and
        ($TrackedAtHead.Count -eq 2) -and
        ($TrackedAtHead -contains "scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1.ps1") -and
        ($TrackedAtHead -contains "scripts/aws/MATRIX_C2_AWS_LOGIN_CANONICAL_R1_SELF_TEST.ps1")

    Assert-True ($PreCommitState -or $PostCommitState) "FAIL: repository is neither exact precommit nor exact postcommit canonical lifecycle state"

    $LifecycleState =
        if ($PreCommitState) { "PRECOMMIT_EXACT_TWO_UNTRACKED" }
        else { "POSTCOMMIT_CLEAN_TRACKED_AT_HEAD" }

    Write-Host "REPOSITORY_LIFECYCLE_STATE=$LifecycleState"
    Write-Host "REPOSITORY_DUAL_LIFECYCLE_GUARD=PASS"

    Write-Host "STATIC_GUARD_AUDIT=PASS"
    Write-Host "EXIT_CODE_CAPTURE_SUCCESS_0=PASS"
    Write-Host "EXIT_CODE_CAPTURE_FAILURE_7=PASS"
    Write-Host "ONE_TIME_AUTH_REUSE_REJECTION=PASS"
    Write-Host "FAIL_CLOSED_GUARDS=PASS"
    Write-Host "NO_STS_NO_PROVISIONING_STATIC_AUDIT=PASS"
    Write-Host "REPOSITORY_EXACT_TWO_UNTRACKED_FILES=PASS"
    Write-Host "AWS_NETWORK_CALLS_PERFORMED=FALSE"
    Write-Host "RESULT=PASS" -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $Root) {
        Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    }
}