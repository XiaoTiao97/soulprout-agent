<#
.SYNOPSIS
    Soulprout Gateway 一键构建脚本（Windows PowerShell）

.DESCRIPTION
    完整构建流程：
      Step 1  安装 Python 依赖（requirements_gateway.txt）
      Step 2  用 PyInstaller 将 gateway/main.py 打包为独立 exe
      Step 3  将打包产物复制到 Tauri sidecar 目录
      Step 4  运行 npm install 安装 Tauri CLI
      Step 5  运行 tauri build 生成最终安装包

.EXAMPLE
    # 在项目根目录执行：
    .\gateway-app\scripts\build.ps1

    # 仅执行打包步骤（跳过依赖安装）：
    .\gateway-app\scripts\build.ps1 -SkipDeps
#>

param(
    [switch]$SkipDeps,      # 跳过 pip install
    [switch]$SkipPyInstaller, # 跳过 PyInstaller（直接用已有的 gateway.exe）
    [switch]$SkipTauri      # 跳过 tauri build（只做 PyInstaller 步骤）
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── 颜色输出辅助 ────────────────────────────────────────────────
function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

# ── 路径 ────────────────────────────────────────────────────────
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir      = Split-Path -Parent $ScriptDir          # gateway-app/
$ProjectRoot = Split-Path -Parent $AppDir             # soulprout-agent/
$GatewayDir  = Join-Path $ProjectRoot 'gateway'
$SpecFile    = Join-Path $GatewayDir 'gateway.spec'
$DistDir     = Join-Path $ProjectRoot 'dist'
$BinariesDir = Join-Path $AppDir 'src-tauri\binaries'

Info "项目根目录: $ProjectRoot"
Info "Gateway 目录: $GatewayDir"

# ── 检测目标三元组（Tauri sidecar 文件名格式）───────────────────
# Windows x86_64 对应：gateway-x86_64-pc-windows-msvc.exe
$RustTarget = (rustup show active-toolchain 2>$null) -replace '\s.*',''
if (-not $RustTarget) {
    $RustTarget = 'x86_64-pc-windows-msvc'
    Warn "无法自动检测 Rust target，使用默认值: $RustTarget"
} else {
    Info "Rust target: $RustTarget"
}
$SidecarName = "gateway-$RustTarget.exe"
$SidecarPath = Join-Path $BinariesDir $SidecarName

# ── Step 1：安装 Python 依赖 ─────────────────────────────────────
if (-not $SkipDeps) {
    Info "Step 1 - 安装 Python 依赖..."
    $ReqFile = Join-Path $GatewayDir 'requirements_gateway.txt'
    python -m pip install --upgrade pip | Out-Null
    python -m pip install pyinstaller | Out-Null
    python -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) { Fail "pip install 失败" }
    Success "Python 依赖安装完成"
} else {
    Warn "Step 1 跳过（-SkipDeps）"
}

# ── Step 2：PyInstaller 打包 gateway ─────────────────────────────
if (-not $SkipPyInstaller) {
    Info "Step 2 - PyInstaller 打包 gateway..."
    Push-Location $ProjectRoot
    try {
        # 清理旧产物
        if (Test-Path (Join-Path $ProjectRoot 'build\gateway')) {
            Remove-Item -Recurse -Force (Join-Path $ProjectRoot 'build\gateway')
        }
        if (Test-Path (Join-Path $DistDir 'gateway.exe')) {
            Remove-Item -Force (Join-Path $DistDir 'gateway.exe')
        }

        python -m PyInstaller $SpecFile --distpath $DistDir --workpath (Join-Path $ProjectRoot 'build')
        if ($LASTEXITCODE -ne 0) { Fail "PyInstaller 打包失败" }
    } finally {
        Pop-Location
    }
    Success "PyInstaller 打包完成 → dist\gateway.exe"
} else {
    Warn "Step 2 跳过（-SkipPyInstaller）"
}

# ── Step 3：复制到 Tauri binaries 目录 ──────────────────────────
Info "Step 3 - 复制 gateway.exe 到 Tauri sidecar 目录..."
$SourceExe = Join-Path $DistDir 'gateway.exe'
if (-not (Test-Path $SourceExe)) {
    Fail "未找到 dist\gateway.exe，请先运行 PyInstaller（去掉 -SkipPyInstaller）"
}

New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
Copy-Item -Path $SourceExe -Destination $SidecarPath -Force
Success "已复制到: $SidecarPath"

# ── Step 4 & 5：npm install + tauri build ───────────────────────
if (-not $SkipTauri) {
    Info "Step 4 - npm install..."
    Push-Location $AppDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { Fail "npm install 失败" }
        Success "npm install 完成"

        Info "Step 5 - tauri build..."
        npm run build
        if ($LASTEXITCODE -ne 0) { Fail "tauri build 失败" }
    } finally {
        Pop-Location
    }

    $InstallerDir = Join-Path $AppDir 'src-tauri\target\release\bundle'
    Success "构建完成！安装包位于: $InstallerDir"
} else {
    Warn "Step 4/5 跳过（-SkipTauri），只需将 $SidecarPath 用于手动 tauri build"
}

Write-Host ""
Success "全部步骤完成 🎉"
