# Soulprout Desktop 构建脚本（Windows PowerShell）
# 在仓库根目录执行：.\desktop\scripts\build.ps1
#
# 步骤：界面（vite）→ sidecar（PyInstaller）→ 外壳（tauri build，产出 NSIS 安装包）
# 结构参考 gateway-app/scripts/build.ps1。

param(
    # 发布版本 X.Y.Z；传入时写回 tauri.conf.json / Cargo.toml
    [string]$Version,
    [string]$Notes,
    [switch]$SkipDeps,
    [switch]$SkipUi,
    [switch]$SkipPyInstaller,
    [switch]$SkipTauri,
    # 指定 Python 解释器（默认用 PATH 里的 python）
    [string]$Python = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir  = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $DesktopDir
$UiDir       = Join-Path $DesktopDir 'ui'
$SidecarDir  = Join-Path $DesktopDir 'sidecar'
$SpecFile    = Join-Path $SidecarDir 'soulprout_desktop.spec'
$TauriDir    = Join-Path $DesktopDir 'src-tauri'
$DistDir     = Join-Path $DesktopDir 'dist'
$ConfPath    = Join-Path $TauriDir 'tauri.conf.json'
$CargoPath   = Join-Path $TauriDir 'Cargo.toml'
$ReleaseDir  = Join-Path $DesktopDir 'release'

function Write-Utf8NoBom($Path, $Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# 外部命令会把普通日志写到 stderr；PowerShell 5.1 在 Stop 模式下会把它当成致命错误，
# 所以临时放宽，改用退出码判断成败。
function Invoke-External([scriptblock]$Command, [string]$ErrorMessage) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { Fail $ErrorMessage }
}

Info "Project root: $ProjectRoot"

if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "Version must be X.Y.Z, got: $Version" }
    $conf = Get-Content $ConfPath -Raw
    $confRe = [regex]'("version"\s*:\s*")[^"]*(")'
    if (-not $confRe.IsMatch($conf)) { Fail 'No version field in tauri.conf.json' }
    Write-Utf8NoBom $ConfPath $confRe.Replace($conf, "`${1}$Version`${2}", 1)
    $cargo = Get-Content $CargoPath -Raw
    $cargoRe = [regex]'(?m)^(version\s*=\s*")[^"]*(")'
    if (-not $cargoRe.IsMatch($cargo)) { Fail 'No version field in Cargo.toml' }
    Write-Utf8NoBom $CargoPath $cargoRe.Replace($cargo, "`${1}$Version`${2}", 1)
    Success "Version set to $Version"
} else {
    $verMatch = [regex]::Match((Get-Content $ConfPath -Raw), '"version"\s*:\s*"([^"]+)"')
    if (-not $verMatch.Success) { Fail 'Cannot read version from tauri.conf.json' }
    $Version = $verMatch.Groups[1].Value
    Info "Version: $Version (from tauri.conf.json)"
}

# ---- 界面 -------------------------------------------------------------
if (-not $SkipUi) {
    Info "Step 1 - Building UI (desktop/ui, 复用 web/node_modules)..."
    $WebModules = Join-Path $ProjectRoot 'web\node_modules'
    if (-not (Test-Path $WebModules)) {
        Info "web/node_modules not found, running npm install in web/ ..."
        Push-Location (Join-Path $ProjectRoot 'web')
        try { Invoke-External { npm install } "npm install (web) failed" } finally { Pop-Location }
    }
    Push-Location $UiDir
    try { Invoke-External { npm run build } "UI build failed" } finally { Pop-Location }
    Success "UI built -> desktop\ui\dist"
} else {
    Warn "Step 1 skipped (-SkipUi)"
}

# ---- Rust 目标三元组 ---------------------------------------------------
$RustTarget = $null
try {
    $hostLine = rustc -Vv 2>$null | Select-String '^host: '
    if ($hostLine) { $RustTarget = ($hostLine.ToString() -replace '^host:\s*', '').Trim() }
} catch {}
if (-not $RustTarget) {
    $RustTarget = 'x86_64-pc-windows-msvc'
    Warn "Cannot detect Rust target, using default: $RustTarget"
} else {
    Info "Rust target: $RustTarget"
}
# PyInstaller 单目录产物，以及 tauri 打包时作为资源带进安装包的暂存目录（安装后位于 <安装目录>\sidecar）
$SidecarDist   = Join-Path $DistDir 'soulprout-desktop-sidecar'
$SidecarBundle = Join-Path $TauriDir 'sidecar-bundle'

# ---- sidecar ----------------------------------------------------------
if (-not $SkipDeps) {
    Info "Step 2 - Installing Python dependencies..."
    Invoke-External { & $Python -m pip install --upgrade pip | Out-Null } "pip upgrade failed"
    Invoke-External { & $Python -m pip install pyinstaller | Out-Null } "pyinstaller install failed"
    Invoke-External { & $Python -m pip install -r (Join-Path $SidecarDir 'requirements.txt') } "pip install failed"
    Success "Python dependencies installed"
} else {
    Warn "Step 2 skipped (-SkipDeps)"
}

if (-not $SkipPyInstaller) {
    Info "Step 3 - PyInstaller packaging sidecar..."
    # conda 环境里 _ctypes 等扩展依赖 Library\bin 下的 DLL（ffi.dll 等）。不在 PATH 里的话 PyInstaller
    # 找不到它们，打出来的 exe 启动就报「DLL load failed while importing _ctypes」。
    $pyExe = (& $Python -c "import sys; print(sys.executable)").Trim()
    $pyDir = Split-Path -Parent $pyExe
    $extra = @($pyDir, (Join-Path $pyDir 'Library\bin'), (Join-Path $pyDir 'Scripts')) | Where-Object { Test-Path $_ }
    $env:PATH = (($extra -join ';') + ';' + $env:PATH)
    Push-Location $ProjectRoot
    try {
        if (Test-Path $SidecarDist) { Remove-Item -Recurse -Force $SidecarDist }
        Invoke-External {
            & $Python -m PyInstaller $SpecFile --distpath $DistDir --workpath (Join-Path $DesktopDir 'build') --noconfirm
        } "PyInstaller build failed"
    } finally { Pop-Location }
    Success "PyInstaller done -> desktop\dist\soulprout-desktop-sidecar\"
} else {
    Warn "Step 3 skipped (-SkipPyInstaller)"
}

$SourceExe = Join-Path $SidecarDist 'soulprout-desktop-sidecar.exe'
if (-not (Test-Path $SourceExe)) { Fail "$SourceExe not found. Run PyInstaller first (remove -SkipPyInstaller)." }
# 整个目录复制进 tauri 的资源暂存目录（先清空，免得残留上一次的文件或开发占位文件）
if (Test-Path $SidecarBundle) { Remove-Item -Recurse -Force $SidecarBundle }
New-Item -ItemType Directory -Force -Path $SidecarBundle | Out-Null
Copy-Item -Path (Join-Path $SidecarDist '*') -Destination $SidecarBundle -Recurse -Force
$fileCount = (Get-ChildItem $SidecarBundle -Recurse -File | Measure-Object).Count
Success "Sidecar staged: $SidecarBundle ($fileCount files)"

# ---- 外壳 -------------------------------------------------------------
if (-not $SkipTauri) {
    Info "Step 4 - npm install (tauri cli)..."
    Push-Location $DesktopDir
    try {
        Invoke-External { npm install } "npm install failed"
        Info "Step 5 - tauri build..."
        Invoke-External { npm run build } "tauri build failed"
    } finally { Pop-Location }

    $NsisDir = Join-Path $TauriDir 'target\release\bundle\nsis'
    if (-not (Test-Path $NsisDir)) { Fail "NSIS output dir not found: $NsisDir" }
    $Installer = Get-ChildItem -Path $NsisDir -Filter "*_${Version}_*-setup.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $Installer) { Fail "No installer matching *_${Version}_*-setup.exe in $NsisDir" }

    if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

    $VersionedName = "Soulprout_${Version}_x64-setup.exe"
    Copy-Item $Installer.FullName (Join-Path $ReleaseDir $VersionedName) -Force
    Copy-Item $Installer.FullName (Join-Path $ReleaseDir 'Soulprout-setup.exe') -Force
    Success "Release: $ReleaseDir\$VersionedName"
    Success "Release: $ReleaseDir\Soulprout-setup.exe (官网下载用固定名)"
} else {
    Warn "Step 4/5 skipped (-SkipTauri). Sidecar ready at: $SidecarBundle"
}

Write-Host ""
Success "All steps finished."
