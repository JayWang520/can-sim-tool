param(
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "未找到虚拟环境，请先运行 install.bat"
}

& $python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "未安装 PyInstaller，正在安装..."
    & $python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 安装失败" }
}

Write-Host "[1/3] PyInstaller 打包中..."
& $python -m PyInstaller --noconfirm --clean (Join-Path $repoRoot "CanSimTool.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$outputDir = Join-Path $repoRoot "dist\CanSimTool"
New-Item -ItemType Directory -Force -Path (Join-Path $outputDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $outputDir "presets") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $outputDir "dbcs\uploads") | Out-Null

Write-Host "[2/3] 复制使用说明和启动脚本..."
Get-ChildItem -LiteralPath (Join-Path $repoRoot "packaging") -File |
    Where-Object { $_.Extension -in ".txt", ".bat" } |
    Copy-Item -Destination $outputDir -Force

if (-not $NoArchive) {
    Write-Host "[3/3] 生成便携版压缩包..."
    $archive = Join-Path $repoRoot "dist\CanSimTool-便携版.zip"
    # Compress-Archive 在 WinPS 5.1 下对含中文的 zip 名会报 "Illegal characters in path"，改用 .NET API
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    [System.IO.Compression.ZipFile]::CreateFromDirectory($outputDir, $archive, [System.IO.Compression.CompressionLevel]::Optimal, $true)
}

Write-Host "打包完成：$outputDir\CanSimTool.exe"
if (-not $NoArchive) { Write-Host "压缩包：$archive" }
