# Soulprout Gateway build script (Windows PowerShell)
# Run from project root: .\gateway-app\scripts\build.ps1

param(
    [switch]$SkipDeps,
    [switch]$SkipPyInstaller,
    [switch]$SkipTauri,
    [switch]$SkipIcons
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir      = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $AppDir
$GatewayDir  = Join-Path $ProjectRoot 'gateway'
$SpecFile    = Join-Path $GatewayDir 'gateway.spec'
$DistDir     = Join-Path $ProjectRoot 'dist'
$BinariesDir = Join-Path $AppDir 'src-tauri\binaries'

Info "Project root: $ProjectRoot"
Info "Gateway dir:  $GatewayDir"

$IconIco = Join-Path $AppDir 'src-tauri\icons\icon.ico'
if ($SkipIcons) {
    Warn "Icon generation skipped (-SkipIcons)"
} elseif (Test-Path $IconIco) {
    Success "Icons already exist, skipping generation ($IconIco)"
} else {
    Info "Generating app icons..."
    python (Join-Path $ScriptDir 'generate-icons.py')
    if ($LASTEXITCODE -ne 0) { Fail "Icon generation failed" }
}

$RustTarget = $null
try {
    $hostLine = rustc -Vv 2>$null | Select-String '^host: '
    if ($hostLine) {
        $RustTarget = ($hostLine.ToString() -replace '^host:\s*', '').Trim()
    }
} catch {}
if (-not $RustTarget) {
    $RustTarget = 'x86_64-pc-windows-msvc'
    Warn "Cannot detect Rust target, using default: $RustTarget"
} else {
    Info "Rust target: $RustTarget"
}
$SidecarName = "gateway-$RustTarget.exe"
$SidecarPath = Join-Path $BinariesDir $SidecarName

if (-not $SkipDeps) {
    Info "Step 1 - Installing Python dependencies..."
    $ReqFile = Join-Path $GatewayDir 'requirements.txt'
    python -m pip install --upgrade pip | Out-Null
    python -m pip install pyinstaller | Out-Null
    python -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }
    Success "Python dependencies installed"
} else {
    Warn "Step 1 skipped (-SkipDeps)"
}

if (-not $SkipPyInstaller) {
    Info "Step 2 - PyInstaller packaging gateway..."
    Push-Location $ProjectRoot
    try {
        if (Test-Path (Join-Path $ProjectRoot 'build\gateway')) {
            Remove-Item -Recurse -Force (Join-Path $ProjectRoot 'build\gateway')
        }
        if (Test-Path (Join-Path $DistDir 'gateway.exe')) {
            Remove-Item -Force (Join-Path $DistDir 'gateway.exe')
        }

        python -m PyInstaller $SpecFile --distpath $DistDir --workpath (Join-Path $ProjectRoot 'build')
        if ($LASTEXITCODE -ne 0) { Fail "PyInstaller build failed" }
    } finally {
        Pop-Location
    }
    Success "PyInstaller done -> dist\gateway.exe"
} else {
    Warn "Step 2 skipped (-SkipPyInstaller)"
}

Info "Step 3 - Copy gateway.exe to Tauri sidecar dir..."
$SourceExe = Join-Path $DistDir 'gateway.exe'
if (-not (Test-Path $SourceExe)) {
    Fail "dist\gateway.exe not found. Run PyInstaller first (remove -SkipPyInstaller)."
}

New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
Copy-Item -Path $SourceExe -Destination $SidecarPath -Force
Success "Copied to: $SidecarPath"

if (-not $SkipTauri) {
    Info "Step 4 - npm install..."
    Push-Location $AppDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { Fail "npm install failed" }
        Success "npm install done"

        Info "Step 5 - tauri build..."
        npm run build
        if ($LASTEXITCODE -ne 0) { Fail "tauri build failed" }
    } finally {
        Pop-Location
    }

    $InstallerDir = Join-Path $AppDir 'src-tauri\target\release\bundle'
    $NsisDir = Join-Path $InstallerDir 'nsis'
    if (Test-Path $NsisDir) {
        $NsisExe = Get-ChildItem (Join-Path $NsisDir '*.exe') |
            Where-Object { $_.Name -ne 'Soulprout-Gateway-setup.exe' } |
            Select-Object -First 1
        if ($NsisExe) {
            $StableInstaller = Join-Path $NsisDir 'Soulprout-Gateway-setup.exe'
            Copy-Item -Path $NsisExe.FullName -Destination $StableInstaller -Force
            Success "Stable installer: $StableInstaller"
        }
    }
    Success "Build complete. Installers at: $InstallerDir"
} else {
    Warn "Step 4/5 skipped (-SkipTauri). Sidecar ready at: $SidecarPath"
}

Write-Host ""
Success "All steps finished."
