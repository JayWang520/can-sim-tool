#!/usr/bin/env bash
# 一键启动：首次运行自动安装依赖；端口被占自动换；自动打开浏览器
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "首次运行，自动安装依赖（约 1-2 分钟）..."
  python3 -m venv .venv || { echo "[!] 创建失败: sudo apt install python3-venv"; exit 1; }
  .venv/bin/pip install --quiet -r requirements.txt || \
    .venv/bin/pip install --quiet -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || \
    { echo "[!] 依赖安装失败"; exit 1; }
fi
exec .venv/bin/python run.py
