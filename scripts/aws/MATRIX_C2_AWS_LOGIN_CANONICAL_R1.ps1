#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$AuthorizationReportPath,
    [Parameter(Mandatory=$true)][string]$AuthorizationReportSha256,
    [Parameter(Mandatory=$true)][string]$AuthorizationBundlePath,
    [Parameter(Mandatory=$true)][string]$AuthorizationBundleSha256,
    [Parameter(Mandatory=$true)][string]$ExpectedBranch,
    [Parameter(Mandatory=$true)][string]$ExpectedHead,
    [string]$Profile = "MATRIX_C2_PROBE",
    [string]$Region = "us-east-2",
    [string]$ExpectedAwsCliVersion = "2.36.31",
    [switch]$OfflineSelfTest,
    [ValidateSet(0,7)][int]$OfflineSelfTestExitCode = 0,
    [string]$StateRootOverride,
    [string]$EvidenceRootOverride
)

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
function Restore-Env {
    param([hashtable]$Old)
    foreach ($Name in $Old.Keys) {
        [Environment]::SetEnvironmentVariable($Name,$Old[$Name],"Process")
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent (Split-Path -Parent $ScriptDir)

$StateRoot =
    if ($OfflineSelfTest -and $StateRootOverride) { $StateRootOverride }
    else { Join-Path $env:LOCALAPPDATA "MATRIX-LAB-SPORTS\C2\aws-login-state" }

$EvidenceRoot =
    if ($OfflineSelfTest -and $EvidenceRootOverride) { $EvidenceRootOverride }
    else { Join-Path $env:USERPROFILE "Downloads\MATRIX_C2_EVIDENCE" }

if (-not $OfflineSelfTest) {
    Assert-True ([string]::IsNullOrWhiteSpace($StateRootOverride)) "FAIL: StateRootOverride allowed only in OfflineSelfTest"
    Assert-True ([string]::IsNullOrWhiteSpace($EvidenceRootOverride)) "FAIL: EvidenceRootOverride allowed only in OfflineSelfTest"
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$RunDir = Join-Path $EvidenceRoot ("CANONICAL_AWS_LOGIN_R1_" + $Stamp)
$Report = Join-Path $RunDir "MATRIX_C2_AWS_LOGIN_CANONICAL_R1.txt"
$ConsumedDir = Join-Path $StateRoot "consumed-authorizations"
$ConsumedMarker = Join-Path $ConsumedDir (($AuthorizationReportSha256.ToLowerInvariant()) + ".aws-login.consumed")
$SessionRoot = Join-Path $StateRoot ("sessions\CANONICAL_R1_" + $Stamp)
$ConfigFile = Join-Path $SessionRoot "config"
$CredentialsFile = Join-Path $SessionRoot "credentials"
$LoginCacheDir = Join-Path $SessionRoot "login-cache"
$ActiveDir = Join-Path $StateRoot "active"
$ActiveLocator = Join-Path $ActiveDir "MATRIX_C2_PROBE.current.psd1"
$OfflineCountFile = Join-Path $StateRoot "offline-subprocess-count.txt"

$OldEnv = @{}
foreach ($Name in @(
    "AWS_CONFIG_FILE","AWS_SHARED_CREDENTIALS_FILE","AWS_LOGIN_CACHE_DIRECTORY",
    "AWS_PROFILE","AWS_REGION","AWS_DEFAULT_REGION","AWS_PAGER","AWS_CLI_AUTO_PROMPT"
)) {
    $OldEnv[$Name] = [Environment]::GetEnvironmentVariable($Name,"Process")
}

try {
    New-Item -ItemType Directory -Force -Path $RunDir,$ConsumedDir,$SessionRoot,$LoginCacheDir,$ActiveDir | Out-Null

    Write-Host ""
    Write-Host "=== MATRIX C2 AWS LOGIN CANONICAL R1 ===" -ForegroundColor Cyan
    Write-Host ("MODE=" + $(if ($OfflineSelfTest) {"OFFLINE_SELF_TEST"} else {"AUTHORIZED_SINGLE_AWS_LOGIN"}))
    Write-Host "MAX_AWS_LOGIN_EXECUTIONS=1"
    Write-Host "STS_CALLS_AUTHORIZED=FALSE"
    Write-Host "RESOURCE_PROVISIONING_AUTHORIZED=FALSE"
    Write-Host "LOGIN_CACHE_CONTENT_READ_BY_WRAPPER=FALSE"
    Write-Host "SECRET_VALUE_READ_BY_WRAPPER=FALSE"

    Assert-True (Test-Path -LiteralPath $AuthorizationReportPath -PathType Leaf) "FAIL: authorization report missing"
    Assert-True (Test-Path -LiteralPath $AuthorizationBundlePath -PathType Leaf) "FAIL: authorization bundle missing"
    Assert-True ((Get-Sha256 -LiteralPath $AuthorizationReportPath) -eq $AuthorizationReportSha256.ToLowerInvariant()) "FAIL: authorization report hash mismatch"
    Assert-True ((Get-Sha256 -LiteralPath $AuthorizationBundlePath) -eq $AuthorizationBundleSha256.ToLowerInvariant()) "FAIL: authorization bundle hash mismatch"

    $AuthText = [System.IO.File]::ReadAllText($AuthorizationReportPath).Replace("`r","")
    Assert-True ($AuthText -match '(?m)^CONTROLLED_SINGLE_AWS_LOGIN_RETRY_AUTHORIZED=TRUE$') "FAIL: exact aws-login authorization flag missing"
    Assert-True ($AuthText -match '(?m)^MAX_AWS_LOGIN_COMMAND_EXECUTIONS_AUTHORIZED=1$') "FAIL: one-execution authorization missing"
    Assert-True ($AuthText -match '(?m)^AWS_LOGIN_RETRY_AFTER_THIS_ATTEMPT_AUTHORIZED=FALSE$') "FAIL: no-retry guard missing"
    Assert-True ($AuthText -match '(?m)^STS_CALLS_AUTHORIZED=FALSE$') "FAIL: STS-forbidden guard missing"
    Assert-True ($AuthText -match '(?m)^RESOURCE_PROVISIONING_AUTHORIZED=FALSE$') "FAIL: provisioning-forbidden guard missing"

    Push-Location $Repo
    try {
        $Branch = (& git branch --show-current 2>$null).Trim()
        $Head = (& git rev-parse HEAD 2>$null).Trim()
        $Dirty = @(& git status --porcelain=v1 --untracked-files=all 2>$null | Where-Object { $_ -and $_.Trim() })
    } finally { Pop-Location }

    Assert-True ($Branch -eq $ExpectedBranch) "FAIL: unexpected branch"
    Assert-True ($Head -eq $ExpectedHead) "FAIL: unexpected HEAD"

    if (-not $OfflineSelfTest) {
        Assert-True ($Dirty.Count -eq 0) "FAIL: repository must be clean for online aws login"
    }

    Assert-True (-not (Test-Path -LiteralPath $ConsumedMarker)) "FAIL: one-time aws-login authorization already consumed"

    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $ConsumedMarker,
        ("authorization_report_sha256=" + $AuthorizationReportSha256.ToLowerInvariant() + "`nconsumed_utc=" + (Get-Date).ToUniversalTime().ToString("o") + "`n"),
        $Utf8NoBom
    )

    Write-Host "AUTHORIZATION_EVIDENCE_CHAIN=PASS"
    Write-Host "ONE_TIME_AUTHORIZATION_CONSUMED=TRUE"

    [Environment]::SetEnvironmentVariable("AWS_CONFIG_FILE",$ConfigFile,"Process")
    [Environment]::SetEnvironmentVariable("AWS_SHARED_CREDENTIALS_FILE",$CredentialsFile,"Process")
    [Environment]::SetEnvironmentVariable("AWS_LOGIN_CACHE_DIRECTORY",$LoginCacheDir,"Process")
    [Environment]::SetEnvironmentVariable("AWS_PROFILE",$Profile,"Process")
    [Environment]::SetEnvironmentVariable("AWS_REGION",$Region,"Process")
    [Environment]::SetEnvironmentVariable("AWS_DEFAULT_REGION",$Region,"Process")
    [Environment]::SetEnvironmentVariable("AWS_PAGER","","Process")
    [Environment]::SetEnvironmentVariable("AWS_CLI_AUTO_PROMPT","off","Process")

    $Psi = New-Object System.Diagnostics.ProcessStartInfo
    $Psi.UseShellExecute = $false
    $Psi.CreateNoWindow = $false

    if ($OfflineSelfTest) {
        $ExistingCount = 0
        if (Test-Path -LiteralPath $OfflineCountFile -PathType Leaf) {
            $ExistingRaw = [System.IO.File]::ReadAllText($OfflineCountFile).Trim()
            if ($ExistingRaw -match '^\d+$') { $ExistingCount = [int]$ExistingRaw }
        }
        [System.IO.File]::WriteAllText($OfflineCountFile,[string]($ExistingCount + 1),$Utf8NoBom)

        $Psi.FileName = $env:ComSpec
        $Psi.Arguments = "/d /c exit $OfflineSelfTestExitCode"
    }
    else {
        $Aws = Get-Command aws.exe -ErrorAction SilentlyContinue
        Assert-True ($null -ne $Aws) "FAIL: aws.exe not found"

        $VersionText = (& $Aws.Source --version 2>&1 | Out-String).Trim()
        Assert-True ($VersionText -match '^aws-cli/([0-9]+\.[0-9]+\.[0-9]+)') "FAIL: AWS CLI version parse failed"
        Assert-True ($Matches[1] -eq $ExpectedAwsCliVersion) "FAIL: unexpected AWS CLI version"

        $Psi.FileName = $Aws.Source
        $Psi.Arguments = "login --profile $Profile --region $Region --no-cli-pager --no-cli-auto-prompt"

        Write-Host "IMPORTANT_BROWSER_INSTRUCTION=TYPE_CURRENT_PASSWORD_MANUALLY_DO_NOT_TRUST_AUTOFILL" -ForegroundColor Yellow
        Write-Host "IMPORTANT_BROWSER_INSTRUCTION=USE_ONLY_CURRENT_AUTHORIZED_MFA_DEVICE" -ForegroundColor Yellow
        Write-Host "IMPORTANT_FAILURE_RULE=NO_RETRY" -ForegroundColor Yellow
    }

    $Proc = New-Object System.Diagnostics.Process
    $Proc.StartInfo = $Psi

    $Started = $Proc.Start()
    Assert-True $Started "FAIL: subprocess did not start"

    $Proc.WaitForExit()
    $Proc.Refresh()
    $ExitCode = [int]$Proc.ExitCode
    $Proc.Dispose()

    Write-Host "AWS_LOGIN_EXIT_CODE=$ExitCode"

    if ($OfflineSelfTest) {
        $Succeeded = ($ExitCode -eq 0)
    }
    else {
        $CacheFiles = @(Get-ChildItem -LiteralPath $LoginCacheDir -File -ErrorAction SilentlyContinue)
        $CacheNonEmpty = @($CacheFiles | Where-Object { $_.Length -gt 0 })
        $ConfigExists = Test-Path -LiteralPath $ConfigFile -PathType Leaf
        $Succeeded = ($ExitCode -eq 0 -and $CacheNonEmpty.Count -gt 0 -and $ConfigExists)
    }

    if ($Succeeded -and -not $OfflineSelfTest) {
        $LocatorLines = @(
            "@{",
            "  Profile = '$Profile'",
            "  Region = '$Region'",
            "  ConfigFile = '$($ConfigFile.Replace("'","''"))'",
            "  CredentialsFile = '$($CredentialsFile.Replace("'","''"))'",
            "  LoginCacheDirectory = '$($LoginCacheDir.Replace("'","''"))'",
            "  CreatedUtc = '$((Get-Date).ToUniversalTime().ToString("o"))'",
            "}"
        )
        [System.IO.File]::WriteAllLines($ActiveLocator,$LocatorLines,$Utf8NoBom)
    }

    $ReportLines = @(
        "=== MATRIX C2 AWS LOGIN CANONICAL R1 ===",
        ("MODE=" + $(if ($OfflineSelfTest) {"OFFLINE_SELF_TEST"} else {"AUTHORIZED_SINGLE_AWS_LOGIN"})),
        "AUTHORIZATION_EVIDENCE_CHAIN=PASS",
        "ONE_TIME_AUTHORIZATION_CONSUMED=TRUE",
        "AUTHORIZATION_REUSABLE=FALSE",
        "AWS_LOGIN_EXECUTION_COUNT=1",
        "AWS_LOGIN_EXIT_CODE=$ExitCode",
        ("AWS_LOGIN_SUCCEEDED=" + $Succeeded.ToString().ToUpperInvariant()),
        "LOGIN_CACHE_CONTENT_READ_BY_WRAPPER=FALSE",
        "SECRET_VALUE_READ_BY_WRAPPER=FALSE",
        "STS_CALLS_PERFORMED=FALSE",
        "RESOURCE_PROVISIONING_PERFORMED=FALSE",
        "AWS_LOGIN_RETRY_AUTHORIZED=FALSE",
        ("RESULT=" + $(if ($Succeeded) {"PASS"} else {"FAIL_CLOSED"}))
    )
    [System.IO.File]::WriteAllLines($Report,$ReportLines,$Utf8NoBom)

    if ($Succeeded) {
        Write-Host "AWS_LOGIN_SUCCEEDED=TRUE" -ForegroundColor Green
        Write-Host "RESULT=PASS" -ForegroundColor Green
        exit 0
    }

    Write-Host "AWS_LOGIN_SUCCEEDED=FALSE" -ForegroundColor Yellow
    Write-Host "RESULT=FAIL_CLOSED" -ForegroundColor Yellow
    exit 1
}
catch {
    Write-Host ""
    Write-Host "=== MATRIX C2 AWS LOGIN CANONICAL R1 ==="
    Write-Host "RESULT=FAIL_CLOSED" -ForegroundColor Red
    Write-Host ("ERROR=" + $_.Exception.Message)
    Write-Host "AWS_LOGIN_RETRY_AUTHORIZED=FALSE"
    Write-Host "STS_CALLS_PERFORMED=FALSE"
    Write-Host "RESOURCE_PROVISIONING_PERFORMED=FALSE"
    exit 1
}
finally {
    Restore-Env -Old $OldEnv
}