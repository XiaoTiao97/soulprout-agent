# Soulprout Gateway build script (Windows PowerShell)
# Run from project root: .\gateway-app\scripts\build.ps1

param(
    # 发布版本号 X.Y.Z。传入时会写回 tauri.conf.json / Cargo.toml；
    # 省略则沿用 tauri.conf.json 里的当前版本。
    [string]$Version,
    # 更新说明，会显示在客户端的「发现新版本」弹窗里。
    [string]$Notes,
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
$ConfPath    = Join-Path $AppDir 'src-tauri\tauri.conf.json'
$CargoPath   = Join-Path $AppDir 'src-tauri\Cargo.toml'
$ReleaseDir  = Join-Path $AppDir 'release'

# latest.json 里安装包 URL 的前缀，需与 tauri.conf.json 的 updater.endpoints 同源
$UpdateBaseUrl = if ($env:GATEWAY_UPDATE_BASE_URL) {
    $env:GATEWAY_UPDATE_BASE_URL.TrimEnd('/')
} else {
    'https://soulprout-gateway-app.oss-cn-hongkong.aliyuncs.com'
}

Info "Project root: $ProjectRoot"
Info "Gateway dir:  $GatewayDir"

function Write-Utf8NoBom($Path, $Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# 调用外部命令（python / npm / pyinstaller）。
# 这些工具会把普通日志写到 stderr，而在 $ErrorActionPreference = 'Stop' 下
# PowerShell 5.1 会把 stderr 输出当成致命错误中断脚本，所以这里临时放宽，
# 改用退出码判断成败。
function Invoke-External([scriptblock]$Command, [string]$ErrorMessage) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { Fail $ErrorMessage }
}

if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "Version must be X.Y.Z, got: $Version" }

    $conf = Get-Content $ConfPath -Raw
    $confRe = [regex]'("version"\s*:\s*")[^"]*(")'
    if (-not $confRe.IsMatch($conf)) { Fail "No version field in tauri.conf.json" }
    Write-Utf8NoBom $ConfPath $confRe.Replace($conf, "`${1}$Version`${2}", 1)

    $cargo = Get-Content $CargoPath -Raw
    $cargoRe = [regex]'(?m)^(version\s*=\s*")[^"]*(")'
    if (-not $cargoRe.IsMatch($cargo)) { Fail "No version field in Cargo.toml" }
    Write-Utf8NoBom $CargoPath $cargoRe.Replace($cargo, "`${1}$Version`${2}", 1)

    Success "Version set to $Version"
} else {
    $verMatch = [regex]::Match((Get-Content $ConfPath -Raw), '"version"\s*:\s*"([^"]+)"')
    if (-not $verMatch.Success) { Fail "Cannot read version from tauri.conf.json" }
    $Version = $verMatch.Groups[1].Value
    Info "Version: $Version (from tauri.conf.json)"
}

if (-not $Notes) { $Notes = "Soulprout Gateway $Version" }

$IconIco = Join-Path $AppDir 'src-tauri\icons\icon.ico'
if ($SkipIcons) {
    Warn "Icon generation skipped (-SkipIcons)"
} elseif (Test-Path $IconIco) {
    Success "Icons already exist, skipping generation ($IconIco)"
} else {
    Info "Generating app icons..."
    Invoke-External { python (Join-Path $ScriptDir 'generate-icons.py') } "Icon generation failed"
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
    Invoke-External { python -m pip install --upgrade pip | Out-Null } "pip upgrade failed"
    Invoke-External { python -m pip install pyinstaller | Out-Null } "pyinstaller install failed"
    Invoke-External { python -m pip install -r $ReqFile } "pip install failed"
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

        Invoke-External {
            python -m PyInstaller $SpecFile --distpath $DistDir --workpath (Join-Path $ProjectRoot 'build')
        } "PyInstaller build failed"
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
        Invoke-External { npm install } "npm install failed"
        Success "npm install done"

        Info "Step 5 - tauri build..."
        Invoke-External { npm run build } "tauri build failed"
    } finally {
        Pop-Location
    }

    Info "Step 6 - Collecting release artifacts..."
    $NsisDir = Join-Path $AppDir 'src-tauri\target\release\bundle\nsis'
    if (-not (Test-Path $NsisDir)) { Fail "NSIS output dir not found: $NsisDir" }

    # 按版本号精确匹配，避免拿到上一次构建残留的安装包
    $Installer = Get-ChildItem -Path $NsisDir -Filter "*_${Version}_*-setup.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $Installer) { Fail "No installer matching *_${Version}_*-setup.exe in $NsisDir" }

    if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

    # Tauri 产出的文件名带空格（"Soulprout Gateway_0.1.1_x64-setup.exe"），
    # 写进下载 URL 得转义，容易出错，所以统一改成无空格的名字
    $VersionedName = "Soulprout-Gateway-$Version-setup.exe"

    # 版本化文件名：自动更新下载用，内容固定可长期缓存
    Copy-Item $Installer.FullName (Join-Path $ReleaseDir $VersionedName) -Force
    # 固定文件名：前端下载按钮用，OSS 上覆盖同名对象，前端无需改代码
    Copy-Item $Installer.FullName (Join-Path $ReleaseDir 'Soulprout-Gateway-setup.exe') -Force
    Success "Installer: $VersionedName"

    # 客户端启动时读这个文件判断有没有新版本
    $manifest = [ordered]@{
        version  = $Version
        notes    = $Notes
        url      = "$UpdateBaseUrl/updates/$Version/$VersionedName"
        pub_date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    # 必须无 BOM：客户端的 JSON 解析器不接受 BOM，否则检查更新会失败
    Write-Utf8NoBom (Join-Path $ReleaseDir 'version.json') ($manifest | ConvertTo-Json -Depth 3)
    Success "Manifest: version.json (version $Version)"

    Success "Release artifacts at: $ReleaseDir"
} else {
    Warn "Step 4/5 skipped (-SkipTauri). Sidecar ready at: $SidecarPath"
}

Write-Host ""
Success "All steps finished."
