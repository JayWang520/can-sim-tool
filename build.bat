@echo off
cd /d %~dp0
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
exit /b %errorlevel%
echo ================= 打包 CAN 工具（Windows 免安装版） ================
if not exist .venv\Scripts\python.exe (
  echo [!] 未找到虚拟环境，请先运行 install.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
  echo [*] 未安装 PyInstaller，尝试安装...
  .venv\Scripts\python.exe -m pip install pyinstaller
  if errorlevel 1 (
    echo [!] PyInstaller 安装失败，请联网后重试
    pause
    exit /b 1
  )
)
echo [1/3] PyInstaller 打包中...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --name CanSimTool ^
  --paths ".venv\Lib\site-packages" ^
  --add-data "web;web" ^
  --add-data "scenarios;scenarios" ^
  --add-data "dbcs;dbcs" ^
  --add-data "presets;presets" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.protocols.websockets.auto" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --collect-submodules "can.interfaces" ^
  --collect-submodules "cantools" ^
  run.py
if errorlevel 1 (
  echo [!] 打包失败，请查看上方错误信息
  pause
  exit /b 1
)
echo [2/3] 准备可写数据目录...
if not exist dist\CanSimTool\logs mkdir dist\CanSimTool\logs
if not exist dist\CanSimTool\presets mkdir dist\CanSimTool\presets
if not exist dist\CanSimTool\dbcs\uploads mkdir dist\CanSimTool\dbcs\uploads
for %%F in (packaging\*.txt) do copy /y "%%~fF" "dist\CanSimTool" >nul
for %%F in (packaging\*.bat) do copy /y "%%~fF" "dist\CanSimTool" >nul
echo [3/3] 生成便携版压缩包...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\CanSimTool' -DestinationPath 'dist\CanSimTool-便携版.zip' -Force"
echo.
echo 打包完成！
echo   目录版： dist\CanSimTool\CanSimTool.exe
echo   压缩包： dist\CanSimTool-便携版.zip
echo 免安装使用：解压后双击 CanSimTool.exe 即可。
pause
