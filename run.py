"""CAN 工具启动器：自动选空闲端口、防重复启动、自动打开浏览器。

用法：
    python run.py [起始端口]        # 默认 8000，被占用则自动向后找
    环境变量 CAN_TOOL_NO_BROWSER=1  # 禁止自动打开浏览器（无桌面环境/调试时用）
"""
import os
import json
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from app.build_info import frontend_version

sys.path.insert(0, str(Path(__file__).parent))

DEFAULT_PORT = 8000


def resource_dir() -> Path:
    root = Path(__file__).resolve().parent
    return Path(getattr(sys, "_MEIPASS", root))


def app_url(port: int, version: str) -> str:
    """Use a versioned URL so browsers cannot reactivate an old live page."""
    return f"http://127.0.0.1:{port}/?v={version}"


def parse_start_port(args: list[str]) -> int:
    if not args:
        return DEFAULT_PORT
    try:
        port = int(args[0])
    except ValueError as exc:
        raise ValueError("端口必须是数字，例如：python run.py 8080") from exc
    if not 1 <= port <= 65535:
        raise ValueError("端口范围必须是 1～65535")
    return port


def port_in_use(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", p))
            return False
        except OSError:
            return True


def is_current_app(port: int, expected_version: str) -> bool:
    """Only reuse an already-running instance built from the same frontend."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as r:
            body = json.load(r)
            return r.status == 200 and body.get("frontend_version") == expected_version
    except Exception:
        return False


def open_browser(url: str) -> None:
    if os.environ.get("CAN_TOOL_NO_BROWSER"):
        return
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    try:
        start = parse_start_port(sys.argv[1:])
    except ValueError as exc:
        print(f"[!] {exc}")
        sys.exit(2)
    expected_version = frontend_version(resource_dir())
    # 已经在跑 → 不重复起，直接打开页面
    if is_current_app(start, expected_version):
        url = app_url(start, expected_version)
        print(f"工具已在运行：{url}（直接打开浏览器）")
        open_browser(url)
        return
    # 端口被其他程序占用 → 从起始端口向后找空闲口
    port = None
    for p in range(start, start + 20):
        if not port_in_use(p):
            port = p
            break
    if port is None:
        print(f"[!] 端口 {start}~{start + 19} 全被占用：python run.py <其他端口> 手动指定")
        sys.exit(1)
    if port != start:
        print(f"[!] 端口 {start} 被占用，自动改用 {port}")

    import uvicorn

    from app.main import app

    url = app_url(port, expected_version)
    print("=" * 50)
    print(f"  CAN 模拟收发工具已启动: {url}")
    print(f"  本机直接访问上面地址；虚拟机/其他电脑访问本机IP:{port}")
    print("=" * 50)
    threading.Timer(2.5, open_browser, args=(url,)).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
