@echo off
setlocal
cd /d "%~dp0"

rem Prefer the current packaged application.
rem Launcher revision: trigger-edit-1
if exist "dist\CanSimTool\CanSimTool.exe" (
  "dist\CanSimTool\CanSimTool.exe" %*
  if errorlevel 1 (
    echo CanSimTool failed to start. Keep the complete _internal folder next to the exe.
    pause
    exit /b 1
  )
  exit /b 0
)

rem Fall back to the source launcher when no packaged build exists.
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment and installing dependencies...
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 or newer is required and must be on PATH.
    pause
    exit /b 1
  )
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create Python environment.
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)

.venv\Scripts\python.exe run.py %*
pause
