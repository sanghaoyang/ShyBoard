# Authenticode-sign ShyBoard portable binaries before packaging.
# Configure a trusted RSA code-signing certificate in CurrentUser/My and set:
#   SHYBOARD_SIGN_THUMBPRINT=<certificate thumbprint>
#   SHYBOARD_TIMESTAMP_URL=<the RFC 3161 URL supplied by the CA>
# Set SHYBOARD_REQUIRE_SIGNING=1 in release CI so an unsigned build fails closed.

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$PortableDir = Join-Path $ProjectRoot "dist\ShyBoard-Portable"
$Thumbprint = ([string]$env:SHYBOARD_SIGN_THUMBPRINT).Replace(" ", "")
$TimestampUrl = [string]$env:SHYBOARD_TIMESTAMP_URL
$RequireSigning = [string]$env:SHYBOARD_REQUIRE_SIGNING -eq "1"

if (-not $Thumbprint) {
    if ($RequireSigning) { throw "SHYBOARD_SIGN_THUMBPRINT is required for release builds" }
    Write-Output "Signing skipped: SHYBOARD_SIGN_THUMBPRINT is not configured"
    exit 0
}
if (-not $TimestampUrl) { throw "SHYBOARD_TIMESTAMP_URL is required when signing" }
if ($Thumbprint -notmatch '^[0-9A-Fa-f]{40,64}$') { throw "Signing certificate thumbprint is invalid" }

$Certificate = Get-ChildItem -LiteralPath "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
if (-not $Certificate.HasPrivateKey) { throw "Signing certificate has no private key" }
$EkuOids = @($Certificate.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value })
if ($EkuOids -notcontains "1.3.6.1.5.5.7.3.3") {
    throw "Certificate is not valid for code signing"
}

$SignTool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
if (-not $SignTool) {
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    $SignTool = Get-ChildItem -LiteralPath $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SignTool) { throw "signtool.exe was not found; install the Windows SDK" }

$Targets = Get-ChildItem -LiteralPath $PortableDir -Recurse -File |
    Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".pyd") }
foreach ($Target in $Targets) {
    $status = (Get-AuthenticodeSignature -LiteralPath $Target.FullName).Status
    if ($status -eq "Valid") { continue }
    & $SignTool sign /sha1 $Thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 /d "ShyBoard" $Target.FullName
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $($Target.FullName)" }
}

foreach ($Target in $Targets) {
    & $SignTool verify /pa /all /q $Target.FullName
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $($Target.FullName)" }
}
Write-Output "Authenticode signatures verified for $($Targets.Count) portable binaries"
