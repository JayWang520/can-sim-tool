@echo off
cd /d %~dp0
if not exist "%~dp0_internal\python311.dll" (
  echo [错误] 找不到 _internal 运行库目录。
  echo 请保留整个 CanSimTool 文件夹，不要单独复制 CanSimTool.exe。
  pause
  exit /b 1
)
start "" "%~dp0CanSimTool.exe"
