# End-to-end tests for the transactional Windows update helper.
param([switch]$KeepArtifacts)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$PortableDir = Join-Path $ProjectRoot "dist\ShyBoard-Portable"
$ReleaseZip = Join-Path $ProjectRoot "dist\ShyBoard-Portable.zip"
$ReleaseManifest = Get-Content -LiteralPath (Join-Path $PortableDir "release.json") -Raw | ConvertFrom-Json
$CurrentVersion = ([string]$ReleaseManifest.version).TrimStart("v")
$TestParent = Join-Path $ProjectRoot "data\update-helper-tests"
$RunRoot = Join-Path $TestParent ([Guid]::NewGuid().ToString("N"))
$AllPassed = $false
$Checks = 0

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
    $script:Checks++
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "") }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Get-FreePort {
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Stop-ExactApp([string]$InstallDir) {
    $targetExe = [IO.Path]::GetFullPath((Join-Path $InstallDir "ShyBoard.exe"))
    try {
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "ShyBoard.exe" -and $_.ExecutablePath -and
            ([IO.Path]::GetFullPath($_.ExecutablePath) -eq $targetExe)
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}
}

function Wait-Health([int]$Port, [string]$ExpectedVersion) {
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/health" -f $Port) -TimeoutSec 1
            if ($health.service -eq "workbench" -and ([string]$health.version).TrimStart("v") -eq $ExpectedVersion.TrimStart("v")) {
                return $true
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function New-TestInstall([string]$Name) {
    $install = Join-Path $RunRoot $Name
    New-Item -ItemType Directory -Force -Path $install | Out-Null
    Copy-Item -LiteralPath (Join-Path $PortableDir "ShyBoard.exe") -Destination $install
    Copy-Item -LiteralPath (Join-Path $PortableDir "ShyBoard-MCP.exe") -Destination $install
    Copy-Item -LiteralPath (Join-Path $PortableDir "update.ps1") -Destination $install
    Copy-Item -LiteralPath (Join-Path $PortableDir "_internal") -Destination $install -Recurse
    $data = Join-Path $install "data"
    $updates = Join-Path $data "updates"
    New-Item -ItemType Directory -Force -Path $updates | Out-Null
    [IO.File]::WriteAllText((Join-Path $data "preserve-me.txt"), "user-data-sentinel")
    [IO.File]::WriteAllText((Join-Path $install "_internal\old-only.marker"), "old-install")
    $port = Get-FreePort
    [IO.File]::WriteAllText((Join-Path $data "port.txt"), [string]$port)
    return @{ Install = $install; Data = $data; Updates = $updates; Port = $port }
}

function Set-PendingPackage($Context, [string]$PackagePath, [string]$Version) {
    $targetZip = Join-Path $Context.Updates "ShyBoard-Portable.zip"
    Copy-Item -LiteralPath $PackagePath -Destination $targetZip -Force
    $pending = @{
        zip = "ShyBoard-Portable.zip"
        version = $Version
        sha256 = Get-Sha256 $targetZip
        size = (Get-Item -LiteralPath $targetZip).Length
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $Context.Updates "pending_update.json"), $pending, (New-Object Text.UTF8Encoding($false)))
}

function Invoke-Helper($Context) {
    $scriptPath = Join-Path $Context.Install "update.ps1"
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $scriptPath -OldPid 0 -HeadlessRestart
    return $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $ReleaseZip)) { throw "Build the release package before running this test." }
foreach ($required in @("ShyBoard.exe", "ShyBoard-MCP.exe", "update.ps1", "_internal", "release.json")) {
    if (-not (Test-Path -LiteralPath (Join-Path $PortableDir $required))) { throw "Portable output is missing $required" }
}

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
$successInstall = $null
$rollbackInstall = $null
try {
    Write-Output "[1/2] Testing successful transactional install..."
    $successInstall = New-TestInstall "success"
    Set-PendingPackage $successInstall $ReleaseZip ("v" + $CurrentVersion)
    $exitCode = Invoke-Helper $successInstall
    Assert-True ($exitCode -eq 0) "successful helper run must exit with code 0"
    Assert-True (Wait-Health $successInstall.Port $CurrentVersion) "updated app must pass the health/version check"
    Assert-True (Test-Path -LiteralPath (Join-Path $successInstall.Install "ShyBoard.exe")) "main executable must be installed"
    Assert-True (Test-Path -LiteralPath (Join-Path $successInstall.Install "ShyBoard-MCP.exe")) "MCP executable must be installed"
    Assert-True (Test-Path -LiteralPath (Join-Path $successInstall.Install "update.ps1")) "update helper must be installed"
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $successInstall.Install "_internal\old-only.marker"))) "obsolete internal files must not survive an update"
    Assert-True ((Get-Content -LiteralPath (Join-Path $successInstall.Data "preserve-me.txt") -Raw) -eq "user-data-sentinel") "user data must be preserved"
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $successInstall.Updates "pending_update.json"))) "pending state must be cleared after success"
    $successResult = Get-Content -LiteralPath (Join-Path $successInstall.Updates "last_result.json") -Raw | ConvertFrom-Json
    Assert-True ($successResult.status -eq "success") "success result must be recorded"
    Stop-ExactApp $successInstall.Install

    Write-Output "[2/2] Testing automatic rollback after a failed version health check..."
    $rollbackInstall = New-TestInstall "rollback"
    $tamperedDir = Join-Path $RunRoot "future-package"
    $tamperedZip = Join-Path $RunRoot "future-package.zip"
    Expand-Archive -LiteralPath $ReleaseZip -DestinationPath $tamperedDir
    $futureManifest = @{ format = "shyboard-release"; version = "9.9.9" } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $tamperedDir "release.json"), $futureManifest, (New-Object Text.UTF8Encoding($false)))
    Compress-Archive -Path (Join-Path $tamperedDir "*") -DestinationPath $tamperedZip -CompressionLevel Optimal
    Set-PendingPackage $rollbackInstall $tamperedZip "v9.9.9"
    $exitCode = Invoke-Helper $rollbackInstall
    Assert-True ($exitCode -ne 0) "failed health/version validation must return a non-zero exit code"
    Assert-True (Wait-Health $rollbackInstall.Port $CurrentVersion) "previous app must restart after rollback"
    Assert-True (Test-Path -LiteralPath (Join-Path $rollbackInstall.Install "_internal\old-only.marker")) "rollback must restore the old internal directory"
    Assert-True ((Get-Content -LiteralPath (Join-Path $rollbackInstall.Data "preserve-me.txt") -Raw) -eq "user-data-sentinel") "rollback must preserve user data"
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $rollbackInstall.Updates "pending_update.json"))) "pending state must be cleared after failure"
    $failedResult = Get-Content -LiteralPath (Join-Path $rollbackInstall.Updates "last_result.json") -Raw | ConvertFrom-Json
    Assert-True ($failedResult.status -eq "failed") "failed result must be recorded"
    Assert-True (([string]$failedResult.message).Contains("previous version was restored")) "failure result must state that rollback occurred"
    Stop-ExactApp $rollbackInstall.Install

    $AllPassed = $true
    Write-Output "RESULT: $Checks helper integration checks passed"
} finally {
    if ($successInstall) { Stop-ExactApp $successInstall.Install }
    if ($rollbackInstall) { Stop-ExactApp $rollbackInstall.Install }
    if ($AllPassed -and -not $KeepArtifacts) {
        $resolvedRoot = [IO.Path]::GetFullPath($RunRoot)
        $resolvedParent = [IO.Path]::GetFullPath($TestParent).TrimEnd('\') + '\'
        if (-not $resolvedRoot.StartsWith($resolvedParent, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean an unsafe test path: $resolvedRoot"
        }
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    } else {
        Write-Output "Test artifacts kept at: $RunRoot"
    }
}
