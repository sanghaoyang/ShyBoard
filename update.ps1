# ShyBoard transactional updater v5.
# This script is intentionally ASCII-only for Windows PowerShell 5.1.
param(
    [int]$OldPid = 0,
    [switch]$NoRestart,
    [switch]$HeadlessRestart
)

$ErrorActionPreference = "Stop"
$Base = [IO.Path]::GetFullPath($PSScriptRoot)
$Data = Join-Path $Base "data"
$DataConfig = Join-Path $Base "data-location.json"
if ($env:SHYBOARD_DATA_DIR) {
    $Data = [IO.Path]::GetFullPath($env:SHYBOARD_DATA_DIR)
} elseif (Test-Path -LiteralPath $DataConfig) {
    try {
        $configuredData = [string]((Get-Content -LiteralPath $DataConfig -Raw | ConvertFrom-Json).path)
        if ($configuredData -and [IO.Path]::IsPathRooted($configuredData)) {
            $Data = [IO.Path]::GetFullPath($configuredData)
        }
    } catch {
        throw "data-location.json is invalid: $($_.Exception.Message)"
    }
}
$Upd = Join-Path $Data "updates"
$Log = Join-Path $Upd "update.log"
$PendingFile = Join-Path $Upd "pending_update.json"
$ResultFile = Join-Path $Upd "last_result.json"
$ExpectedZip = "ShyBoard-Portable.zip"
$Exe = Join-Path $Base "ShyBoard.exe"
$McpExe = Join-Path $Base "ShyBoard-MCP.exe"
$Internal = Join-Path $Base "_internal"
$SelfScript = Join-Path $Base "update.ps1"
$Stage = $null
$Backup = $null
$InstallTouched = $false
$StartedProcess = $null
$PendingVersion = ""

New-Item -ItemType Directory -Force -Path $Upd | Out-Null

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $Log -Value $line -Encoding ASCII
}

function Write-Result([string]$Status, [string]$Version, [string]$Message) {
    $payload = @{
        status = $Status
        version = $Version
        message = $Message
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    } | ConvertTo-Json -Compress
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($ResultFile, $payload, $utf8)
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "") }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($fullParent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe path outside expected directory: $fullPath"
    }
    return $fullPath
}

function Remove-ExactPath([string]$Path, [string]$Parent) {
    $safe = Assert-ChildPath $Path $Parent
    if (Test-Path -LiteralPath $safe) {
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}

function Stop-InstalledInstances {
    try {
        $targets = Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "ShyBoard.exe" -and
            $_.ExecutablePath -and
            ([IO.Path]::GetFullPath($_.ExecutablePath) -eq $Exe)
        }
        foreach ($target in $targets) {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        }
        if ($targets) { Start-Sleep -Milliseconds 800 }
    } catch {
        Write-Log "WARN: could not enumerate sibling processes: $($_.Exception.Message)"
    }
}

function Get-RestartArgs {
    $argsList = @()
    $portFile = Join-Path $Data "port.txt"
    if (Test-Path -LiteralPath $portFile) {
        $portText = (Get-Content -LiteralPath $portFile -Raw).Trim()
        $portNumber = 0
        if ([int]::TryParse($portText, [ref]$portNumber) -and $portNumber -ge 1024 -and $portNumber -le 65535) {
            $argsList = @("--port", [string]$portNumber)
        }
    }
    if ($HeadlessRestart) { $argsList += "--no-window" }
    return $argsList
}

function Start-InstalledApp([bool]$VerifyVersion) {
    if ($NoRestart) {
        Write-Log "NoRestart enabled; skipping application launch"
        return $null
    }
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "ShyBoard.exe is missing after install"
    }
    $restartArgs = @(Get-RestartArgs)
    $process = Start-Process -FilePath $Exe -ArgumentList $restartArgs -WorkingDirectory $Base -PassThru
    Write-Log "started ShyBoard pid=$($process.Id)"
    if (-not $VerifyVersion) { return $process }

    $port = 17890
    $portIndex = [Array]::IndexOf($restartArgs, "--port")
    if ($portIndex -ge 0 -and $portIndex + 1 -lt $restartArgs.Count) { $port = [int]$restartArgs[$portIndex + 1] }
    $expected = $PendingVersion.TrimStart('v')
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) { throw "updated application exited before health check" }
        try {
            $health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/health" -f $port) -TimeoutSec 2
            if ($health.service -eq "workbench") {
                $actual = ([string]$health.version).TrimStart('v')
                if ($actual -ne $expected) {
                    throw "version check failed: expected $expected, got $actual"
                }
                Write-Log "health check passed, version=$actual"
                return $process
            }
        } catch {
            if ($_.Exception.Message -like "version check failed:*") { throw }
        }
    }
    throw "updated application health check timed out"
}

function Restore-PreviousInstall {
    Write-Log "rolling back previous installation"
    Stop-InstalledInstances
    if ($StartedProcess -and -not $StartedProcess.HasExited) {
        Stop-Process -Id $StartedProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $Backup -or -not (Test-Path -LiteralPath $Backup)) {
        Write-Log "WARN: backup directory is unavailable"
        return
    }
    Remove-ExactPath $Internal $Base
    foreach ($filePath in @($Exe, $McpExe)) {
        if (Test-Path -LiteralPath $filePath) { Remove-Item -LiteralPath $filePath -Force }
    }
    $oldExe = Join-Path $Backup "ShyBoard.exe"
    $oldMcp = Join-Path $Backup "ShyBoard-MCP.exe"
    $oldInternal = Join-Path $Backup "_internal"
    $oldScript = Join-Path $Backup "update.ps1"
    if (Test-Path -LiteralPath $oldExe) { Move-Item -LiteralPath $oldExe -Destination $Exe -Force }
    if (Test-Path -LiteralPath $oldMcp) { Move-Item -LiteralPath $oldMcp -Destination $McpExe -Force }
    if (Test-Path -LiteralPath $oldInternal) { Move-Item -LiteralPath $oldInternal -Destination $Internal -Force }
    if (Test-Path -LiteralPath $oldScript) { Copy-Item -LiteralPath $oldScript -Destination $SelfScript -Force }
    Write-Log "rollback completed"
}

Write-Log "updater v5 started, OldPid=$OldPid Base=$Base"

try {
    if ($OldPid -gt 0) {
        $waited = 0
        while ($waited -lt 90 -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
            Start-Sleep -Seconds 1
            $waited++
        }
        if ($waited -ge 90) {
            Write-Log "old process did not exit in time; stopping pid=$OldPid"
            Stop-Process -Id $OldPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    }
    Stop-InstalledInstances

    if (-not (Test-Path -LiteralPath $PendingFile)) { throw "pending_update.json is missing" }
    $pending = Get-Content -LiteralPath $PendingFile -Raw | ConvertFrom-Json
    $zipName = [string]$pending.zip
    $PendingVersion = [string]$pending.version
    $expectedHash = ([string]$pending.sha256).ToLowerInvariant()
    $expectedSize = [int64]$pending.size
    if ($zipName -ne $ExpectedZip) { throw "pending package name is invalid" }
    if ($PendingVersion -notmatch '^v?\d+\.\d+\.\d+$') { throw "pending version is invalid" }
    if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "pending SHA-256 is invalid" }

    $zipPath = Assert-ChildPath (Join-Path $Upd $zipName) $Upd
    if (-not (Test-Path -LiteralPath $zipPath)) { throw "pending package is missing" }
    if ((Get-Item -LiteralPath $zipPath).Length -ne $expectedSize) { throw "pending package size mismatch" }
    $actualHash = Get-Sha256 $zipPath
    if ($actualHash -ne $expectedHash) { throw "pending package SHA-256 mismatch" }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $entryName = $entry.FullName.Replace('\', '/')
            if ($entryName.StartsWith('/') -or $entryName.Contains('../') -or $entryName.Contains(':')) {
                throw "package contains an unsafe path"
            }
        }
    } finally { $archive.Dispose() }

    $token = [Guid]::NewGuid().ToString('N')
    $Stage = Assert-ChildPath (Join-Path $Upd ("stage-" + $token)) $Upd
    $Backup = Assert-ChildPath (Join-Path $Upd ("backup-" + $token)) $Upd
    New-Item -ItemType Directory -Path $Stage | Out-Null
    New-Item -ItemType Directory -Path $Backup | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $Stage -Force
    # Downloaded ZIPs can carry Mark-of-the-Web into extracted managed DLLs.
    # Remove only the alternate Zone.Identifier stream before installation.
    Get-ChildItem -LiteralPath $Stage -Recurse -File | Unblock-File -ErrorAction Stop
    Write-Log "download zone markers removed from staged files"

    $srcExe = Join-Path $Stage "ShyBoard.exe"
    $srcMcp = Join-Path $Stage "ShyBoard-MCP.exe"
    $srcInternal = Join-Path $Stage "_internal"
    $srcScript = Join-Path $Stage "update.ps1"
    $srcManifest = Join-Path $Stage "release.json"
    foreach ($required in @($srcExe, $srcMcp, $srcInternal, $srcScript, $srcManifest)) {
        if (-not (Test-Path -LiteralPath $required)) { throw "package structure is incomplete" }
    }
    $manifest = Get-Content -LiteralPath $srcManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.format -ne "shyboard-release") { throw "release manifest format is invalid" }
    if (([string]$manifest.version).TrimStart('v') -ne $PendingVersion.TrimStart('v')) {
        throw "release manifest version does not match pending version"
    }
    if ((Get-Item -LiteralPath $srcExe).Length -le 0 -or (Get-Item -LiteralPath $srcMcp).Length -le 0) {
        throw "package executable is empty"
    }
    Write-Log "preflight validation passed for $PendingVersion"

    if (Test-Path -LiteralPath $Exe) { Move-Item -LiteralPath $Exe -Destination (Join-Path $Backup "ShyBoard.exe") -Force }
    if (Test-Path -LiteralPath $McpExe) { Move-Item -LiteralPath $McpExe -Destination (Join-Path $Backup "ShyBoard-MCP.exe") -Force }
    if (Test-Path -LiteralPath $Internal) { Move-Item -LiteralPath $Internal -Destination (Join-Path $Backup "_internal") -Force }
    if (Test-Path -LiteralPath $SelfScript) { Copy-Item -LiteralPath $SelfScript -Destination (Join-Path $Backup "update.ps1") -Force }
    $InstallTouched = $true

    Copy-Item -LiteralPath $srcExe -Destination $Exe -Force
    Copy-Item -LiteralPath $srcMcp -Destination $McpExe -Force
    Move-Item -LiteralPath $srcInternal -Destination $Internal -Force
    Copy-Item -LiteralPath $srcScript -Destination $SelfScript -Force
    if ((Get-Sha256 $Exe) -ne (Get-Sha256 $srcExe)) {
        throw "installed ShyBoard.exe verification failed"
    }
    if ((Get-Sha256 $McpExe) -ne (Get-Sha256 $srcMcp)) {
        throw "installed ShyBoard-MCP.exe verification failed"
    }
    Write-Log "files installed and verified"

    $StartedProcess = Start-InstalledApp $true
    Write-Result "success" $PendingVersion "Update installed and verified."
    Remove-ExactPath $Stage $Upd
    Remove-ExactPath $Backup $Upd
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PendingFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Upd "check_cache.json") -Force -ErrorAction SilentlyContinue
    Write-Log "update completed successfully"
    exit 0
} catch {
    $failure = $_.Exception.Message
    Write-Log "ERROR: $failure"
    if ($InstallTouched) {
        try { Restore-PreviousInstall }
        catch { Write-Log "FATAL: rollback failed: $($_.Exception.Message)" }
    }
    if ($Stage) {
        try { Remove-ExactPath $Stage $Upd } catch {}
    }
    if ($Backup) {
        try { Remove-ExactPath $Backup $Upd } catch {}
    }
    Remove-Item -LiteralPath $PendingFile -Force -ErrorAction SilentlyContinue
    Write-Result "failed" $PendingVersion ("Update failed and the previous version was restored: " + $failure)
    if (-not $NoRestart) {
        try { Start-InstalledApp $false | Out-Null }
        catch { Write-Log "FATAL: failed to restart previous version: $($_.Exception.Message)" }
    }
    exit 1
}
