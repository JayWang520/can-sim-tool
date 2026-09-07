"""多后端 CAN 总线管理。

同一套代码在 Windows / Linux 运行，运行时选择后端：
- virtual     : python-can 虚拟总线（无需硬件，开发与自动化测试）
- socketcan   : Linux 内核 CAN（PCAN/CANable 等，通道如 can0，需先 ip link up）
- pcan        : PCAN-Basic 库（Windows/Linux，需装 Peak 驱动）
- canalystii  : 周立功 CANalyst-II（python-can 自带后端，需 canalystii 包）
- slcan        : 串口 slcan 固件（CANable 等，通道 COM3 或 /dev/ttyUSB0）
- kvaser      : Kvaser CANlib（需装 CANlib SDK）
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import can

# 后端元信息：value 传给 can.Bus(interface=...)，desc 供前端下拉展示
INTERFACES = {
    "virtual": "虚拟总线（无需硬件，回环测试）",
    "socketcan": "Linux SocketCAN（PCAN/CANable 等，通道 can0）",
    "pcan": "PCAN-Basic（Windows/Linux，通道 PCAN_USBBUS1）",
    "canalystii": "周立功 CANalyst-II（通道 0）",
    "slcan": "串口 slcan（CANable 等，COM3 / /dev/ttyUSB0）",
    "kvaser": "Kvaser CANlib（通道 0）",
    "ixxat": "IXXAT VCI（USB-to-CAN V2 等，通道 0）",
}

# 这些后端在打开时接受 bitrate 参数
_BITRATE_BACKENDS = {"pcan", "canalystii", "slcan", "kvaser", "ixxat"}


def _find_ixxat_vci_dll() -> Optional[Path]:
    """在常见安装位置查找 IXXAT VCI 的 vcinpl.dll，便于驱动装在非标准路径时也能加载。"""
    if sys.platform != "win32":
        return None
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates = [
        system_root / "System32" / "vcinpl.dll",
        system_root / "SysWOW64" / "vcinpl.dll",
    ]
    for base in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        if not base.exists():
            continue
        for vendor in ("IXXAT", "HMS"):
            vendor_dir = base / vendor
            if vendor_dir.exists():
                try:
                    candidates.extend(vendor_dir.rglob("vcinpl*.dll"))
                except OSError:
                    pass
    for dll in candidates:
        try:
            if dll.is_file():
                return dll
        except OSError:
            pass
    return None


def _setup_ixxat_vci_path() -> bool:
    """若找到 vcinpl.dll，将其目录加入 DLL 搜索路径；返回是否找到。"""
    dll = _find_ixxat_vci_dll()
    if dll is None:
        return False
    dll_dir = str(dll.parent)
    if dll_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(dll_dir)
        except Exception:
            pass
    return True


@dataclass
class BusStats:
    received: int = 0
    sent: int = 0
    error_frames: int = 0
    connected_at: Optional[float] = None


class BusService:
    """持有 can.Bus，后台线程收帧并分发给监听者；发送同时以 tx 方向回播。

    监听者回调在接收线程中执行，必须快速返回（只做入队等轻量操作）。
    """

    def __init__(self) -> None:
        self._bus: Optional[can.BusABC] = None
        self._iface_name: Optional[str] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self.stats = BusStats()
        self.frame_stats: dict[tuple[bool, int], dict] = {}
        # cb(message, direction: "rx"|"tx")
        self.listeners: list[Callable[[can.Message, str], None]] = []

    # ------------------------------------------------------------------ state
    @property
    def connected(self) -> bool:
        return self._bus is not None

    def info(self) -> dict:
        with self._lock:
            return {
                "connected": self._bus is not None,
                "interface": self._iface_name,
                "channel": getattr(self._bus, "channel_info", None) if self._bus else None,
                "stats": {
                    "received": self.stats.received,
                    "sent": self.stats.sent,
                    "error_frames": self.stats.error_frames,
                    "uptime_s": round(time.time() - self.stats.connected_at, 1)
                    if self.stats.connected_at
                    else 0,
                },
            }

    def frame_statistics(self) -> list[dict]:
        with self._lock:
            rows = []
            for (extended, arbitration_id), item in self.frame_stats.items():
                rows.append({
                    "extended": extended,
                    "id": f"{arbitration_id:08X}" if extended else f"{arbitration_id:03X}",
                    **item,
                })
        return sorted(rows, key=lambda row: (-row["count"], row["id"]))

    # --------------------------------------------------------------- connect
    def connect(self, interface: str, channel: str, bitrate: int = 250_000) -> dict:
        with self._lock:
            if self.connected:
                raise RuntimeError("总线已连接，请先断开")
            if interface not in INTERFACES:
                raise ValueError(f"不支持的后端: {interface}")
            if not isinstance(bitrate, int) or bitrate <= 0:
                raise ValueError("波特率必须是正整数")
            kwargs: dict = {}
            if interface == "virtual":
                kwargs["receive_own_messages"] = True
            elif interface in _BITRATE_BACKENDS:
                kwargs["bitrate"] = bitrate
            if interface == "ixxat" and not _setup_ixxat_vci_path():
                raise RuntimeError(
                    "未找到 IXXAT VCI 驱动（vcinpl.dll）。请先从 IXXAT 官网安装 VCI Driver 并重启；"
                    "如果已安装但不在 PATH，请把 vcinpl.dll 所在目录加入 PATH 或复制到 System32。"
                )
            try:
                bus = can.Bus(interface=interface, channel=channel, **kwargs)
            except Exception as e:  # 缺驱动/DLL/通道不存在等，统一转成可读错误
                raise RuntimeError(f"打开 {interface} 通道 {channel} 失败: {e}") from e

            self._bus = bus
            self._iface_name = interface
            self.stats = BusStats(connected_at=time.time())
            self.frame_stats = {}
            self._running = True
            self._rx_thread = threading.Thread(
                target=self._rx_loop, args=(bus,), name="can-rx", daemon=True
            )
            self._rx_thread.start()
        return self.info()

    def disconnect(self) -> dict:
        with self._lock:
            self._running = False
            bus, self._bus = self._bus, None
            thread, self._rx_thread = self._rx_thread, None
            self.frame_stats = {}
        if bus is not None:
            try:
                bus.shutdown()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        return self.info()

    # ------------------------------------------------------------------- io
    def send(self, arbitration_id: int, data: bytes, is_extended_id: bool = True) -> None:
        data = bytes(data)
        if len(data) > 8:
            raise ValueError("CAN 数据长度不能超过 8 字节")
        msg = can.Message(
            arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id
        )
        with self._lock:
            bus = self._bus
        if bus is None:
            raise RuntimeError("总线未连接")
        try:
            bus.send(msg)
        except can.CanError as e:
            raise RuntimeError(f"CAN 发送失败: {e}") from e
        except Exception as e:
            if not self.connected:
                raise RuntimeError("总线未连接") from e
            raise
        self.stats.sent += 1
        self._update_frame_stat(msg)
        self._notify(msg, "tx")

    # ------------------------------------------------------------------ loop
    def _rx_loop(self, bus: can.BusABC) -> None:
        while self._running and self._bus is bus:
            try:
                msg = bus.recv(timeout=0.2)
            except can.CanError:
                self.stats.error_frames += 1
                continue
            except Exception:
                break  # 总线被关闭
            if msg is None:
                continue
            if msg.is_error_frame:
                self.stats.error_frames += 1
            self.stats.received += 1
            self._update_frame_stat(msg)
            self._notify(msg, "rx")

    def _update_frame_stat(self, msg: can.Message) -> None:
        key = (bool(msg.is_extended_id), msg.arbitration_id)
        now = time.monotonic()
        with self._lock:
            item = self.frame_stats.get(key)
            if item is None:
                self.frame_stats[key] = {
                    "count": 1, "last_ts": now, "avg_period_ms": None,
                    "min_period_ms": None, "max_period_ms": None,
                }
                return
            delta_ms = (now - item["last_ts"]) * 1000
            item["count"] += 1
            item["last_ts"] = now
            periods = item["count"] - 1
            previous_avg = item["avg_period_ms"]
            item["avg_period_ms"] = round(
                delta_ms if previous_avg is None else (previous_avg * (periods - 1) + delta_ms) / periods, 3
            )
            item["min_period_ms"] = round(
                delta_ms if item["min_period_ms"] is None else min(item["min_period_ms"], delta_ms), 3
            )
            item["max_period_ms"] = round(
                delta_ms if item["max_period_ms"] is None else max(item["max_period_ms"], delta_ms), 3
            )

    def _notify(self, msg: can.Message, direction: str) -> None:
        for cb in list(self.listeners):
            try:
                cb(msg, direction)
            except Exception:
                pass  # 单个监听者出错不影响总线
