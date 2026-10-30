# Soulprout Desktop 发版：写版本号 → 构建 → 上传 OSS（官网按钮 + 版本归档）
#
#   .\desktop\scripts\release.ps1 -Version 0.1.5
#   .\desktop\scripts\release.ps1              # 在 tauri.conf.json 版本上自动 patch +1
#   .\desktop\scripts\release.ps1 -UploadOnly -Version 0.1.5
#
# OSS 布局（与 web/src/constants/downloads.js 一致）：
#   desktop/Soulprout-setup.exe                         ← 官网「下载 Windows 版」
#   desktop/updates/<version>/Soulprout_<version>_x64-setup.exe

param(
    [string]$Version,
    [string]$Notes,
    [switch]$NoUpload,
    [switch]$UploadOnly,
    [switch]$SkipDeps,
    [string]$Python = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

if ($NoUpload -and $UploadOnly) { Fail '-NoUpload 与 -UploadOnly 不能同时使用' }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir  = Split-Path -Parent $ScriptDir
$ConfPath    = Join-Path $DesktopDir 'src-tauri\tauri.conf.json'
$ReleaseDir  = Join-Path $DesktopDir 'release'
$ConfigPath  = Join-Path (Split-Path -Parent $DesktopDir) 'gateway-app\.release.local.json'
$ToolsDir    = Join-Path (Split-Path -Parent $DesktopDir) 'gateway-app\scripts\.tools'

$OssutilVersion = '2.3.0'
$OssutilSha256  = '98209156987667b39fd12a0c7b940342900daef61a9306ea7f34acf17f287da2'

$config = $null
if (-not $NoUpload) {
    if (-not (Test-Path $ConfigPath)) { Fail "缺少 OSS 配置：$ConfigPath（参考 gateway-app/README.md）" }
    $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    foreach ($field in 'accessKeyId', 'accessKeySecret', 'bucket', 'region') {
        if (-not $config.$field) { Fail "$ConfigPath 缺少 $field" }
    }
}

$current = [regex]::Match((Get-Content $ConfPath -Raw), '"version"\s*:\s*"([^"]+)"')
if (-not $current.Success) { Fail '无法读取 tauri.conf.json 版本号' }
$currentVersion = $current.Groups[1].Value

if ($Version -and $Version -notmatch '^\d+\.\d+\.\d+$') {
    Fail "版本号须为 X.Y.Z，收到：$Version"
}

if ($UploadOnly) {
    if (-not $Version) { $Version = $currentVersion }
    Info "仅上传 release 目录中的 $Version"
} elseif (-not $Version) {
    $parts = $currentVersion.Split('.')
    if ($parts.Count -ne 3) { Fail "当前版本格式异常：$currentVersion" }
    $Version = "$($parts[0]).$($parts[1]).$([int]$parts[2] + 1)"
    Info "版本 $currentVersion -> $Version（自动 +1，可用 -Version 指定）"
} else {
    Info "版本 $currentVersion -> $Version"
}

if ($UploadOnly) {
    Info '跳过构建'
} else {
    $buildArgs = @{ Version = $Version; Python = $Python }
    if ($SkipDeps) { $buildArgs['SkipDeps'] = $true }
    Info '开始构建（UI → PyInstaller → Tauri NSIS）...'
    & (Join-Path $ScriptDir 'build.ps1') @buildArgs
    if ($LASTEXITCODE -ne 0) { Fail '构建失败' }
}

$versioned = Join-Path $ReleaseDir "Soulprout_${Version}_x64-setup.exe"
$stable    = Join-Path $ReleaseDir 'Soulprout-setup.exe'
if (-not (Test-Path $versioned)) { Fail "未找到 $versioned，请先构建" }
if (-not (Test-Path $stable)) { Fail "未找到 $stable" }

$builtVer = [regex]::Match($versioned, 'Soulprout_(\d+\.\d+\.\d+)_').Groups[1].Value
if ($builtVer -ne $Version) { Fail "安装包文件名版本 $builtVer 与目标 $Version 不一致" }

if ($NoUpload) {
    Success "构建完成（未上传）：$ReleaseDir"
    exit 0
}

$ossutil = Join-Path $ToolsDir 'ossutil.exe'
if (-not (Test-Path $ossutil)) { Fail "未找到 ossutil：$ossutil（先跑一次 gateway-app/scripts/release.ps1）" }

$env:OSS_ACCESS_KEY_ID     = $config.accessKeyId
$env:OSS_ACCESS_KEY_SECRET = $config.accessKeySecret
$env:OSS_REGION            = $config.region
$bucket = "oss://$($config.bucket)"

function Push-Object($LocalPath, $RemoteKey, [string[]]$ExtraArgs) {
    Info "upload $RemoteKey"
    $ossArgs = @('cp', $LocalPath, "$bucket/$RemoteKey", '-f', '--acl', 'public-read') + $ExtraArgs
    & $ossutil @ossArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "上传失败：$RemoteKey" }
    Success "已上传 $RemoteKey"
}

Push-Object $versioned "desktop/updates/$Version/Soulprout_${Version}_x64-setup.exe" `
    @('--cache-control', 'public, max-age=31536000')
Push-Object $stable 'desktop/Soulprout-setup.exe' `
    @('--cache-control', 'no-cache')

$hash = (Get-FileHash $versioned -Algorithm SHA256).Hash
Write-Host ''
Success "Desktop $Version 已发布"
Write-Host "  官网下载: https://oss.soulprout.com/desktop/Soulprout-setup.exe" -ForegroundColor Cyan
Write-Host "  版本归档: https://oss.soulprout.com/desktop/updates/$Version/Soulprout_${Version}_x64-setup.exe" -ForegroundColor Cyan
Write-Host "  SHA256: $hash" -ForegroundColor DarkGray
