# Soulprout Desktop 构建脚本（Windows PowerShell）
# 在仓库根目录执行：.\desktop\scripts\build.ps1
#
# 步骤：界面（vite）→ sidecar（PyInstaller）→ 外壳（tauri build，产出 NSIS 安装包）
# 结构参考 gateway-app/scripts/build.ps1。

param(
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
$BinariesDir = Join-Path $TauriDir 'binaries'
$DistDir     = Join-Path $DesktopDir 'dist'

# 外部命令会把普通日志写到 stderr；PowerShell 5.1 在 Stop 模式下会把它当成致命错误，
# 所以临时放宽，改用退出码判断成败。
function Invoke-External([scriptblock]$Command, [string]$ErrorMessage) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { Fail $ErrorMessage }
}

Info "Project root: $ProjectRoot"

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
$SidecarName = "soulprout-desktop-sidecar-$RustTarget.exe"
$SidecarPath = Join-Path $BinariesDir $SidecarName

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
        $exe = Join-Path $DistDir 'soulprout-desktop-sidecar.exe'
        if (Test-Path $exe) { Remove-Item -Force $exe }
        Invoke-External {
            & $Python -m PyInstaller $SpecFile --distpath $DistDir --workpath (Join-Path $DesktopDir 'build') --noconfirm
        } "PyInstaller build failed"
    } finally { Pop-Location }
    Success "PyInstaller done -> desktop\dist\soulprout-desktop-sidecar.exe"
} else {
    Warn "Step 3 skipped (-SkipPyInstaller)"
}

$SourceExe = Join-Path $DistDir 'soulprout-desktop-sidecar.exe'
if (-not (Test-Path $SourceExe)) { Fail "$SourceExe not found. Run PyInstaller first (remove -SkipPyInstaller)." }
New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
Copy-Item -Path $SourceExe -Destination $SidecarPath -Force
Success "Copied to: $SidecarPath"

# ---- 外壳 -------------------------------------------------------------
if (-not $SkipTauri) {
    Info "Step 4 - npm install (tauri cli)..."
    Push-Location $DesktopDir
    try {
        Invoke-External { npm install } "npm install failed"
        Info "Step 5 - tauri build..."
        Invoke-External { npm run build } "tauri build failed"
    } finally { Pop-Location }
    Success "Installer at: $(Join-Path $TauriDir 'target\release\bundle\nsis')"
} else {
    Warn "Step 4/5 skipped (-SkipTauri). Sidecar ready at: $SidecarPath"
}

Write-Host ""
Success "All steps finished."
