"""报文记录（CSV/ASC）与回放。"""
from __future__ import annotations

import asyncio
import csv
import math
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import can

from .bus import BusService

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class CanLogger:
    def __init__(self, bus: BusService) -> None:
        self._bus = bus
        self._file = None
        self._writer: Optional[csv.writer] = None
        self._fmt = "csv"
        self._t0 = 0.0
        self.count = 0
        self._asc_f = None

    @property
    def recording(self) -> bool:
        return self._file is not None

    def start(self, fmt: str = "csv") -> dict:
        if self.recording:
            raise RuntimeError("已在记录中")
        LOG_DIR.mkdir(exist_ok=True)
        self._fmt = fmt if fmt in ("csv", "asc") else "csv"
        stem = time.strftime("%Y%m%d_%H%M%S")
        name = stem + "." + self._fmt
        if (LOG_DIR / name).exists():
            name = f"{stem}_{uuid.uuid4().hex[:6]}.{self._fmt}"
        path = LOG_DIR / name
        self._t0 = time.monotonic()
        self.count = 0
        if self._fmt == "csv":
            self._file = open(path, "w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._file)
            self._writer.writerow(["ts", "id", "extended", "dir", "dlc", "data"])
        else:
            self._file = open(path, "w", encoding="utf-8")
            self._file.write(
                f"date {time.strftime('%a %b %d %H:%M:%S %Y')}\n"
                "base hex timestamps absolute\n"
                "internal events logged\n"
            )
        return {"recording": True, "file": name, "format": self._fmt}

    def record(self, msg: can.Message, direction: str) -> None:
        if not self.recording:
            return
        ts = time.monotonic() - self._t0
        data_hex = bytes(msg.data).hex().upper()
        if self._fmt == "csv":
            self._writer.writerow(
                [f"{ts:.6f}", f"{msg.arbitration_id:08X}", int(msg.is_extended_id),
                 direction, len(msg.data), data_hex]
            )
        else:
            ext = "x" if msg.is_extended_id else ""
            self._file.write(
                f"{ts:12.6f} 1  {msg.arbitration_id:08X}{ext}   {direction.upper()}"
                f"   d {len(msg.data)} {data_hex}\n"
            )
        self._file.flush()
        self.count += 1

    def stop(self) -> dict:
        if self._file:
            self._file.close()
        name = getattr(self._file, "name", "")
        self._file = None
        self._writer = None
        return {"recording": False, "file": name.split("\\")[-1].split("/")[-1] if name else None,
                "frames": self.count}

    def files(self) -> list[dict]:
        LOG_DIR.mkdir(exist_ok=True)
        out = []
        for p in sorted(LOG_DIR.iterdir(), reverse=True):
            if p.suffix in (".csv", ".asc"):
                out.append({"name": p.name, "size": p.stat().st_size})
        return out


class Replayer:
    def __init__(self, bus: BusService) -> None:
        self._bus = bus
        self._task: Optional[asyncio.Task] = None
        self._file: Optional[str] = None
        self._current = 0
        self._total = 0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, file_name: str, speed: float = 1.0) -> dict:
        if self.running:
            raise RuntimeError("回放进行中")
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("回放倍速必须是有限的正数")
        path = LOG_DIR / Path(file_name).name  # 防路径穿越
        if not path.exists() or path.suffix not in (".csv", ".asc"):
            raise FileNotFoundError(f"仅支持回放本工具记录的 CSV/ASC: {file_name}")
        rows = []
        if path.suffix == ".csv":
            with open(path, newline="", encoding="utf-8") as f:
                rows.extend(csv.DictReader(f))
        else:
            pattern = re.compile(
                r"^\s*(?P<ts>\S+)\s+\S+\s+(?P<id>[0-9A-Fa-f]+)(?P<ext>x)?\s+"
                r"(?P<dir>RX|TX)\s+d\s+(?P<dlc>\d+)\s+(?P<data>[0-9A-Fa-f]*)\s*$",
                re.IGNORECASE,
            )
            for line in path.read_text(encoding="utf-8").splitlines():
                match = pattern.match(line)
                if match:
                    rows.append({
                        "ts": match["ts"], "id": match["id"],
                        "extended": "1" if match["ext"] else "0",
                        "data": match["data"],
                    })
        if not rows:
            raise ValueError("日志为空")

        self._file = path.name
        self._current = 0
        self._total = len(rows)

        async def run() -> None:
            try:
                prev_ts = float(rows[0]["ts"])
                for row in rows:
                    delta = (float(row["ts"]) - prev_ts) / max(speed, 0.01)
                    if delta > 0:
                        await asyncio.sleep(delta)
                    prev_ts = float(row["ts"])
                    try:
                        self._bus.send(
                            int(row["id"], 16), bytes.fromhex(row["data"]),
                            bool(int(row["extended"])),
                        )
                    except RuntimeError:
                        return
                    self._current += 1
            finally:
                self._task = None

        self._task = asyncio.get_running_loop().create_task(run())
        return {"replaying": True, "file": path.name, "frames": len(rows), "speed": speed}

    def stop(self) -> dict:
        if self._task:
            self._task.cancel()
            self._task = None
        return self.status()

    def status(self) -> dict:
        return {
            "replaying": self.running,
            "file": self._file,
            "current": self._current,
            "total": self._total,
        }
