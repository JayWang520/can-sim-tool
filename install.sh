#!/usr/bin/env bash
# 一键安装（Ubuntu/Debian）：缺 python3-venv 时提示安装
cd "$(dirname "$0")"
echo "================= 一键安装 CAN 工具 ================="
if ! command -v python3 >/dev/null; then
  echo "[!] 未找到 python3，请先安装: sudo apt install python3 python3-venv python3-pip"
  exit 1
fi
echo "[1/2] 创建虚拟环境..."
python3 -m venv .venv || { echo "[!] 创建失败，试试: sudo apt install python3-venv"; exit 1; }
echo "[2/2] 安装依赖（失败自动换清华镜像重试）..."
.venv/bin/pip install --quiet -r requirements.txt || \
  .venv/bin/pip install --quiet -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || \
  { echo "[!] 依赖安装失败，请检查网络"; exit 1; }
echo
echo "安装完成！运行 ./run.sh 一键启动"
