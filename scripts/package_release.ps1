# Build ShyBoard-Portable.zip and its SHA-256 sidecar.
param([string]$ExpectedVersion = "")

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$PortableDir = Join-Path $ProjectRoot "dist\ShyBoard-Portable"
$ZipPath = Join-Path $ProjectRoot "dist\ShyBoard-Portable.zip"
$ChecksumPath = $ZipPath + ".sha256"
$AppSource = Get-Content -LiteralPath (Join-Path $ProjectRoot "app.py") -Raw
$match = [regex]::Match($AppSource, 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"')
if (-not $match.Success) { throw "Cannot read APP_VERSION from app.py" }
$Version = $match.Groups[1].Value
if ($ExpectedVersion) {
    $normalized = $ExpectedVersion.TrimStart('v')
    if ($normalized -ne $Version) { throw "Tag version $normalized does not match APP_VERSION $Version" }
}
foreach ($required in @("ShyBoard.exe", "ShyBoard-MCP.exe", "update.ps1", "_internal")) {
    if (-not (Test-Path -LiteralPath (Join-Path $PortableDir $required))) {
        throw "Portable package is missing $required"
    }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "") }
    finally { $sha.Dispose(); $stream.Dispose() }
}
$manifest = @{ format = "shyboard-release"; version = $Version } | ConvertTo-Json -Compress
[IO.File]::WriteAllText((Join-Path $PortableDir "release.json"), $manifest, $utf8)
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
if (Test-Path -LiteralPath $ChecksumPath) { Remove-Item -LiteralPath $ChecksumPath -Force }
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$hash = Get-Sha256 $ZipPath
[IO.File]::WriteAllText($ChecksumPath, "$hash  ShyBoard-Portable.zip`n", $utf8)
Write-Output "Release package: $ZipPath"
Write-Output "SHA-256: $hash"
