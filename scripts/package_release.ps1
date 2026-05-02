param(
    [string]$Version = "",
    [string]$DistDir = "dist"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = (Get-Content -Raw "VERSION").Trim()
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "VERSION is empty."
}

$distPath = Join-Path $repoRoot $DistDir
$bindDir = Join-Path $distPath "rwrsb_bind"
$animDir = Join-Path $distPath "rwrsb_anim"

foreach ($required in @($bindDir, $animDir)) {
    if (-not (Test-Path $required -PathType Container)) {
        throw "Missing build output: $required. Run build.bat first."
    }
}

$sevenZip = Get-Command "7z" -ErrorAction SilentlyContinue
if (-not $sevenZip) {
    $sevenZip = Get-Command "7za" -ErrorAction SilentlyContinue
}
if (-not $sevenZip) {
    $programFiles7z = Join-Path $env:ProgramFiles "7-Zip\7z.exe"
    if (Test-Path $programFiles7z) {
        $sevenZip = Get-Item $programFiles7z
    }
}
if (-not $sevenZip) {
    throw "7-Zip was not found. Install 7-Zip or make 7z.exe available in PATH."
}

$packageName = "rwrsb_gui-v$Version-windows"
$stagingDir = Join-Path $distPath ("_package_" + [Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $distPath "$packageName.7z"

if (Test-Path $archivePath) {
    try {
        Remove-Item -LiteralPath $archivePath -Force
    }
    catch {
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $archivePath = Join-Path $distPath "$packageName-$timestamp.7z"
        Write-Warning "Could not overwrite existing archive. Writing to: $archivePath"
    }
}

New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
Copy-Item -LiteralPath $bindDir -Destination (Join-Path $stagingDir "rwrsb_bind") -Recurse
Copy-Item -LiteralPath $animDir -Destination (Join-Path $stagingDir "rwrsb_anim") -Recurse

foreach ($file in @("README.md", "README_EN.md", "LICENSE", "VERSION")) {
    if (Test-Path $file -PathType Leaf) {
        Copy-Item -LiteralPath $file -Destination $stagingDir
    }
}

$packageReadme = "docs\release\PACKAGE_README.md"
if (Test-Path $packageReadme -PathType Leaf) {
    Copy-Item -LiteralPath $packageReadme -Destination (Join-Path $stagingDir "PACKAGE_README.md")
}

Push-Location $stagingDir
try {
    & $sevenZip.Source a -t7z -mx=9 $archivePath "rwrsb_bind" "rwrsb_anim" "README.md" "README_EN.md" "LICENSE" "VERSION" "PACKAGE_README.md"
    if ($LASTEXITCODE -ne 0) {
        throw "7-Zip failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

try {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
catch {
    Write-Warning "Could not remove temporary staging directory: $stagingDir"
}

Write-Host "Release package created:"
Write-Host "  $archivePath"
