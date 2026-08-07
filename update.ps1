# ============================================================
#  ShyBoard Updater v4 (PowerShell) - Clash Verge Rev style
#  All comments ASCII only (PS 5.1 parses .ps1 with ANSI/GBK
#  unless BOM; Chinese comments would garble the script).
#
#  Design (borrowed from Clash Verge Rev's updater.rs):
#    * Download and install are DECOUPLED. The main app only
#      writes a pending_update.json + zip; it never replaces
#      files while running.
#    * This helper runs as an INDEPENDENT process spawned with
#      DETACHED_PROCESS + DEVNULL stdio, so it never inherits
#      the GUI's invalid handles (the bat used to block on
#      `set /p` with no stdin - root cause of "stuck update").
#    * It waits for the old process (OldPid) to exit, then
#      replaces exe/_internal, verifies sizes, restarts.
#    * Any failure is logged; the zip is kept so the next
#      launch can retry (pending cache preserved).
#
#  Args:
#    -OldPid   PID of the app instance that spawned us.
#              We wait for it to exit before touching files.
# ============================================================
param([int]$OldPid = 0)

$ErrorActionPreference = "Stop"
$Base = $PSScriptRoot
$Data = Join-Path $Base "data"
$Upd  = Join-Path $Data "updates"
$Log  = Join-Path $Upd "update.log"
$PendingFile = Join-Path $Upd "pending_update.json"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $Log -Value $line -Encoding ASCII
}

try {
    New-Item -ItemType Directory -Force -Path $Upd | Out-Null
} catch {}
Write-Log "updater v4 started, OldPid=$OldPid cwd=$Base"

# ---- 1. wait for the old app process to exit (max 60s) ----
# The GUI called os._exit() right after spawning us, so this
# should return almost immediately. Loop is a safety net.
if ($OldPid -gt 0) {
    $waited = 0
    while ($waited -lt 60) {
        $proc = Get-Process -Id $OldPid -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        Start-Sleep -Seconds 1
        $waited++
    }
    if ($waited -ge 60) {
        Write-Log "WARN: OldPid $OldPid still alive after 60s, killing it"
        Stop-Process -Id $OldPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    } else {
        Write-Log "old process $OldPid exited after ${waited}s"
    }
} else {
    Write-Log "no OldPid given, assuming app already exited"
}

# ---- 2. read pending cache ----
if (-not (Test-Path $PendingFile)) {
    Write-Log "FATAL: no pending_update.json, nothing to install"
    exit 1
}
$pending = Get-Content $PendingFile -Raw | ConvertFrom-Json
$zipName = [string]$pending.zip
$version = [string]$pending.version
Write-Log "pending update: version=$version zip=$zipName"
if (-not $zipName) {
    Write-Log "FATAL: pending zip name empty"
    exit 1
}
$zipPath = Join-Path $Upd $zipName
if (-not (Test-Path $zipPath)) {
    Write-Log "FATAL: zip not found: $zipPath"
    exit 1
}

# ---- 3. extract to temp dir ----
$Tmp = Join-Path $Base "__update_tmp"
if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp }
New-Item -ItemType Directory -Path $Tmp | Out-Null
Write-Log "extracting $zipName ..."
Expand-Archive -Path $zipPath -DestinationPath $Tmp -Force
$srcExe = Join-Path $Tmp "ShyBoard.exe"
if (-not (Test-Path $srcExe)) {
    Write-Log "FATAL: extracted zip has no ShyBoard.exe"
    Remove-Item -Recurse -Force $Tmp
    exit 1
}
$srcSize = (Get-Item $srcExe).Length
Write-Log "extract OK, src exe size=$srcSize"

# ---- 4. replace exe (with size verification) ----
$exe = Join-Path $Base "ShyBoard.exe"
Remove-Item $exe -Force -ErrorAction SilentlyContinue
Copy-Item $srcExe $exe -Force
$newSize = (Get-Item $exe).Length
Write-Log "installed exe size=$newSize"
if ($newSize -ne $srcSize) {
    Write-Log "FATAL: exe size mismatch, update aborted"
    Remove-Item -Recurse -Force $Tmp
    exit 1
}
Write-Log "exe replaced and verified OK"

# ---- 5. replace _internal ----
$internal = Join-Path $Base "_internal"
if (Test-Path $internal) { Remove-Item -Recurse -Force $internal }
$srcInternal = Join-Path $Tmp "_internal"
if (Test-Path $srcInternal) {
    Copy-Item $srcInternal $internal -Recurse -Force
    Write-Log "_internal replaced"
} else {
    Write-Log "WARN: zip has no _internal, skipping"
}

# ---- 6. cleanup ----
Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item $PendingFile -Force -ErrorAction SilentlyContinue
Write-Log "cleanup done"

# ---- 7. restart with original port ----
# Port is stored in data/port.txt by the app itself; pass it
# back via --port so the restarted instance keeps its port.
$restartArgs = @()
$portFile = Join-Path $Data "port.txt"
if (Test-Path $portFile) {
    $port = (Get-Content $portFile -Raw).Trim()
    if ($port -match '^\d+$') {
        $restartArgs = @("--port", $port)
        Write-Log "restarting with port $port"
    }
}
try {
    Start-Process -FilePath (Join-Path $Base "ShyBoard.exe") -ArgumentList $restartArgs -WorkingDirectory $Base
    Write-Log "restarted ShyBoard"
} catch {
    Write-Log "FATAL: restart failed: $_"
    exit 1
}

Write-Log "updater v4 done"
exit 0
