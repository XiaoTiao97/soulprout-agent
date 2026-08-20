# Soulprout Gateway 一键发版
#
#   .\gateway-app\scripts\release.ps1 -Notes "修复微信断线重连"
#
# 做三件事：递增版本号 -> 构建安装包 -> 上传阿里云 OSS。
# 上传完成后，已安装的客户端下次启动就会提示更新。
#
# 构建成功但上传失败时，加 -UploadOnly 重试，直接上传已构建的产物。
#
# 首次使用需要在 gateway-app\.release.local.json 里填阿里云 AccessKey，
# 直接运行本脚本会自动生成模板文件。

param(
    # 版本号 X.Y.Z，省略则在当前版本上自动 +1（patch）
    [string]$Version,
    # 更新说明，会显示在用户的「发现新版本」弹窗里
    [string]$Notes,
    # 只构建，不上传（本地验证用）
    [switch]$NoUpload,
    # 只上传，不构建：直接发布 release 目录里已有的产物。
    # 构建成功但上传失败（如凭证问题）时用它重试，省掉十几分钟重新构建。
    [switch]$UploadOnly,
    # 传给 build.ps1：依赖已装好时可跳过 pip install
    [switch]$SkipDeps
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

if ($NoUpload -and $UploadOnly) { Fail '-NoUpload 和 -UploadOnly 不能同时用' }

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir     = Split-Path -Parent $ScriptDir
$ConfPath   = Join-Path $AppDir 'src-tauri\tauri.conf.json'
$ReleaseDir = Join-Path $AppDir 'release'
$ConfigPath = Join-Path $AppDir '.release.local.json'
$ToolsDir   = Join-Path $ScriptDir '.tools'

$OssutilVersion = '2.3.0'
$OssutilSha256  = '98209156987667b39fd12a0c7b940342900daef61a9306ea7f34acf17f287da2'

# ---------------------------------------------------------------------------
# 1. 读取上传配置
# ---------------------------------------------------------------------------

$config = $null
if (-not $NoUpload) {
    if (-not (Test-Path $ConfigPath)) {
        $template = [ordered]@{
            accessKeyId     = ''
            accessKeySecret = ''
            bucket          = 'soulprout-gateway-app'
            region          = 'cn-hongkong'
        }
        [System.IO.File]::WriteAllText(
            $ConfigPath,
            ($template | ConvertTo-Json -Depth 3),
            (New-Object System.Text.UTF8Encoding($false))
        )
        Warn "已生成配置模板：$ConfigPath"
        Warn '请填入阿里云 AccessKey 后重新运行。只需填一次，该文件不会进入 git。'
        Warn '临时只想构建不上传，可加 -NoUpload 参数。'
        exit 1
    }

    $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    foreach ($field in 'accessKeyId', 'accessKeySecret', 'bucket', 'region') {
        if (-not $config.$field) { Fail "$ConfigPath 里缺少 $field" }
    }
    Success "上传目标：oss://$($config.bucket) ($($config.region))"
}

# ---------------------------------------------------------------------------
# 2. 确定版本号
# ---------------------------------------------------------------------------

$current = [regex]::Match((Get-Content $ConfPath -Raw), '"version"\s*:\s*"([^"]+)"')
if (-not $current.Success) { Fail "无法从 tauri.conf.json 读取当前版本号" }
$currentVersion = $current.Groups[1].Value

if ($Version -and $Version -notmatch '^\d+\.\d+\.\d+$') {
    Fail "版本号要写成 X.Y.Z 的形式，收到：$Version"
}

if ($UploadOnly) {
    # 不能递增：要上传的是已经构建好的那个版本
    if (-not $Version) { $Version = $currentVersion }
    Info "仅上传模式，发布 release 目录里已构建的 $Version"
} elseif (-not $Version) {
    $parts = $currentVersion.Split('.')
    if ($parts.Count -ne 3) { Fail "当前版本号格式异常：$currentVersion" }
    $Version = "$($parts[0]).$($parts[1]).$([int]$parts[2] + 1)"
    Info "版本号 $currentVersion -> $Version（自动递增，可用 -Version 指定）"
} else {
    Info "版本号 $currentVersion -> $Version"
}

# ---------------------------------------------------------------------------
# 3. 构建
# ---------------------------------------------------------------------------

if ($UploadOnly) {
    Info '跳过构建（-UploadOnly）'
} else {
    # 必须用哈希表 splatting：数组 splatting 会把元素当成位置参数，
    # '-Version' 会被 build.ps1 当作 $Version 的值而不是参数名
    $buildArgs = @{ Version = $Version }
    if ($Notes)    { $buildArgs['Notes'] = $Notes }
    if ($SkipDeps) { $buildArgs['SkipDeps'] = $true }

    Info '开始构建，PyInstaller 打包加 Rust 编译大约需要十几分钟...'
    & (Join-Path $ScriptDir 'build.ps1') @buildArgs
    if ($LASTEXITCODE -ne 0) { Fail '构建失败，上面有具体错误' }
}

$installer = Get-Item (Join-Path $ReleaseDir "Soulprout-Gateway-$Version-setup.exe") -ErrorAction SilentlyContinue
if (-not $installer) { Fail "没找到 $Version 的安装包，检查构建输出" }
$manifest = Join-Path $ReleaseDir 'version.json'
if (-not (Test-Path $manifest)) { Fail "没找到 version.json" }

# 客户端只认 version.json 里的版本号，它必须和安装包的上传路径对得上，
# 否则用户会收到更新提示却下载到 404
$manifestText = [System.IO.File]::ReadAllText($manifest, [System.Text.Encoding]::UTF8)
$manifestVersion = ($manifestText | ConvertFrom-Json).version
if ($manifestVersion -ne $Version) {
    Fail "version.json 里是 $manifestVersion，要发布的是 $Version，两者不一致；去掉 -UploadOnly 重新构建"
}

if ($NoUpload) {
    Write-Host ''
    Success "构建完成（未上传）：$ReleaseDir"
    exit 0
}

# ---------------------------------------------------------------------------
# 4. 准备 ossutil（首次会下载，之后复用）
# ---------------------------------------------------------------------------

$ossutil = Join-Path $ToolsDir 'ossutil.exe'
if (-not (Test-Path $ossutil)) {
    Info '首次运行，下载阿里云 ossutil 上传工具...'
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $zip = Join-Path $ToolsDir "ossutil-$OssutilVersion.zip"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest "https://gosspublic.alicdn.com/ossutil/v2/$OssutilVersion/ossutil-$OssutilVersion-windows-amd64.zip" -OutFile $zip

    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $OssutilSha256) { Fail "ossutil 校验和不匹配，下载可能被篡改：$actual" }

    $unzipDir = Join-Path $ToolsDir 'unzip'
    Expand-Archive $zip -DestinationPath $unzipDir -Force
    $found = Get-ChildItem $unzipDir -Recurse -Filter 'ossutil.exe' | Select-Object -First 1
    if (-not $found) { Fail 'ossutil.exe 不在压缩包里' }
    Copy-Item $found.FullName $ossutil -Force
    Remove-Item -Recurse -Force $unzipDir, $zip
    Success "ossutil 就绪：$ossutil"
}

# ---------------------------------------------------------------------------
# 5. 上传
# ---------------------------------------------------------------------------

# 凭证只存在于当前进程的环境变量里，不写入任何文件
$env:OSS_ACCESS_KEY_ID     = $config.accessKeyId
$env:OSS_ACCESS_KEY_SECRET = $config.accessKeySecret
$env:OSS_REGION            = $config.region
$bucket = "oss://$($config.bucket)"

function Push-Object($LocalPath, $RemoteKey, [string[]]$ExtraArgs) {
    $ossArgs = @('cp', $LocalPath, "$bucket/$RemoteKey", '-f', '--acl', 'public-read') + $ExtraArgs
    & $ossutil @ossArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "上传失败：$RemoteKey" }
    Success "已上传 $RemoteKey"
}

Info '上传到 OSS...'

# 带版本号的安装包，自动更新从这里下载；内容固定，可长期缓存
Push-Object $installer.FullName "updates/$Version/$($installer.Name)" `
    @('--cache-control', 'public, max-age=31536000')

# 固定文件名，前端下载按钮用；每次覆盖，所以不能缓存
Push-Object (Join-Path $ReleaseDir 'Soulprout-Gateway-setup.exe') 'Soulprout-Gateway-setup.exe' `
    @('--cache-control', 'no-cache')

# 版本清单最后传，确保客户端看到新版本号时安装包已经在线
Push-Object $manifest 'updates/version.json' `
    @('--cache-control', 'no-cache, no-store', '--content-type', 'application/json')

$baseUrl = "https://$($config.bucket).oss-$($config.region).aliyuncs.com"

Write-Host ''
Success "$Version 发布完成"
Write-Host ''
Write-Host '验证清单是否生效（浏览器打开应看到 version 为新版本号）：'
Write-Host "  $baseUrl/updates/version.json" -ForegroundColor Cyan
Write-Host '用户下载地址（前端按钮指向这里，无需改动）：'
Write-Host "  $baseUrl/Soulprout-Gateway-setup.exe" -ForegroundColor Cyan
Write-Host ''
Write-Host '已安装的客户端下次启动时会提示更新。'
