# 下载「唤醒词」功能所需的 sherpa-onnx Android 库（AAR 约 47MB，不进 git）。
# 用法（在 web/android 目录下）：  powershell -ExecutionPolicy Bypass -File .\fetch-wake-deps.ps1
# 模型文件（约 4.7MB）已放在 app/src/main/assets/kws/，无需再下载。

$ErrorActionPreference = 'Stop'
$version = '2.0.0'
$libs = Join-Path $PSScriptRoot 'app\libs'
$aar = Join-Path $libs "sherpa-onnx-$version.aar"
New-Item -ItemType Directory -Force -Path $libs | Out-Null

if (Test-Path $aar) {
    Write-Host "已存在: $aar"
    exit 0
}

$url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/v$version/sherpa-onnx-$version.aar"
Write-Host "下载 $url"
curl.exe -L --retry 3 -o $aar $url
if (-not (Test-Path $aar) -or (Get-Item $aar).Length -lt 10MB) {
    Remove-Item $aar -ErrorAction SilentlyContinue
    throw '下载失败，请检查网络（需要能访问 github.com）'
}
Write-Host "完成: $aar"
