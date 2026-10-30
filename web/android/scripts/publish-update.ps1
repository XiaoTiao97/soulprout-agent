# Publish Android APK + force-update manifest to Aliyun OSS.
#
#   .\web\android\scripts\publish-update.ps1 -ApkPath .\app-release.apk -Version 1.0.1 -VersionCode 2 -Notes "fix wake"
#
# Reuses gateway-app\.release.local.json for OSS credentials.

param(
    [Parameter(Mandatory = $true)][string]$ApkPath,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][int]$VersionCode,
    [string]$Notes = '',
    [string]$ConfigPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Fail($msg)    { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir '..\..\..')).Path
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $RepoRoot 'gateway-app\.release.local.json'
}

if (-not (Test-Path $ApkPath)) { Fail "APK not found: $ApkPath" }
if (-not (Test-Path $ConfigPath)) {
    Fail "OSS config missing: $ConfigPath (see gateway-app/README.md)"
}

$config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($field in 'accessKeyId', 'accessKeySecret', 'bucket', 'region') {
    if (-not $config.$field) { Fail "Missing $field in $ConfigPath" }
}

# 清单里的下载地址必须走自定义域名。bucket.oss-cn-hangzhou.aliyuncs.com
# 在绑定了 CNAME 后会对 APK 返回 HTTP 400，手机点「立即更新」就会失败。
$baseUrl = if ($env:ANDROID_UPDATE_BASE_URL) {
    $env:ANDROID_UPDATE_BASE_URL.TrimEnd('/')
} else {
    'https://oss.soulprout.com'
}

$versionedKey = "android/updates/$Version/Soulprout-$Version.apk"
$stableKey    = 'android/Soulprout.apk'
$manifestKey  = 'android/updates/version.json'
$versionedUrl = "$baseUrl/$versionedKey"

$work = Join-Path $env:TEMP ("soulprout-android-release-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$manifestPath = Join-Path $work 'version.json'

$manifest = [ordered]@{
    version     = $Version
    versionCode = $VersionCode
    notes       = $Notes
    url         = $versionedUrl
    pub_date    = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 3),
    (New-Object System.Text.UTF8Encoding($false))
)

$ossutil = Join-Path $RepoRoot 'gateway-app\scripts\.tools\ossutil.exe'
if (-not (Test-Path $ossutil)) {
    Fail "ossutil not found: $ossutil (run gateway-app/scripts/release.ps1 once)"
}

$env:OSS_ACCESS_KEY_ID     = $config.accessKeyId
$env:OSS_ACCESS_KEY_SECRET = $config.accessKeySecret
$env:OSS_REGION            = $config.region
$bucket = "oss://$($config.bucket)"

function Push-Object([string]$LocalPath, [string]$RemoteKey, [string[]]$ExtraArgs) {
    Info "upload $RemoteKey"
    $ossArgs = @('cp', $LocalPath, "$bucket/$RemoteKey", '-f', '--acl', 'public-read') + $ExtraArgs
    & $ossutil @ossArgs
    if ($LASTEXITCODE -ne 0) { Fail "upload failed: $RemoteKey" }
    Success "uploaded $RemoteKey"
}

try {
    $apkResolved = (Resolve-Path $ApkPath).Path
    Push-Object $apkResolved $versionedKey @('--cache-control', 'public, max-age=31536000')
    Push-Object $apkResolved $stableKey @('--cache-control', 'no-cache')
    Push-Object $manifestPath $manifestKey @('--cache-control', 'no-cache, no-store', '--content-type', 'application/json')
    Write-Host ''
    Success "Published Android $Version (versionCode $VersionCode)"
    Write-Host "  $baseUrl/$stableKey" -ForegroundColor Cyan
    Write-Host "  $versionedUrl" -ForegroundColor Cyan
    Write-Host "  $baseUrl/$manifestKey" -ForegroundColor Cyan
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
    Remove-Item Env:OSS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
    Remove-Item Env:OSS_ACCESS_KEY_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:OSS_REGION -ErrorAction SilentlyContinue
}
