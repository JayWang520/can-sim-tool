@echo off
cd /d %~dp0
chcp 65001 >nul
echo ================= 一键安装 CAN 工具 ================
where python >nul 2>nul
if errorlevel 1 (
  echo [!] 未找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH
  pause & exit /b 1
)
echo [1/3] 创建虚拟环境...
python -m venv .venv
if errorlevel 1 (echo 创建虚拟环境失败 & pause & exit /b 1)
echo [2/3] 升级 pip...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
echo [3/3] 安装依赖（失败自动换清华镜像重试）...
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (echo 依赖安装失败，请检查网络后重试 & pause & exit /b 1)
)
echo.
echo 安装完成！双击 run.bat 一键启动（会自动打开浏览器）
pause
