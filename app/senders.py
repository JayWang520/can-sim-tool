"""通用 CAN 发送：手动单帧 + 周期任务（运行中可在线修改，支持数据递增模式）。"""
from __future__ import annotations

import asyncio
import random
import uuid
from typing import Optional

import can

from .bus import BusService


class Senders:
    """周期发送任务管理。

    - fixed 模式：每周期发送固定数据
    - list 模式：按 data_list 顺序循环；每次启动从第一项开始
    - increment 模式：指定字节区间 [inc_byte, inc_end]（小端拼成整数）按步长递增，
      到区间上限自动回绕；单字节递增即 inc_byte == inc_end
    - 运行中 update() 修改数据/周期/模式，下一周期立即生效
    """

    def __init__(self, bus: BusService) -> None:
        self._bus = bus
        self._tasks: dict[str, dict] = {}  # id -> {config, task}

    # ----------------------------------------------------------------- CRUD
    def create(
        self,
        name: str,
        arbitration_id: int,
        data_hex: str,
        period_ms: int,
        is_extended_id: bool = True,
        auto_start: bool = True,
        mode: str = "fixed",
        inc_byte: int = 0,
        inc_step: int = 1,
        inc_end: int = None,
        data_list: Optional[list[str]] = None,
        random_seed: int = 0,
        random_mask: str = "",
        ramp_min: int = 0,
        ramp_max: int = 255,
    ) -> dict:
        sid = uuid.uuid4().hex[:8]
        entry = {
            "config": {
                "id": sid,
                "name": name,
                "arbitration_id": arbitration_id,
                "data_hex": data_hex.replace(" ", ""),
                "period_ms": period_ms,
                "is_extended_id": is_extended_id,
                "mode": mode,
                "inc_byte": inc_byte,
                "inc_end": inc_byte if inc_end is None else inc_end,
                "inc_step": inc_step,
                "data_list": [] if data_list is None else data_list,
                "random_seed": random_seed,
                "random_mask": random_mask,
                "ramp_min": ramp_min,
                "ramp_max": ramp_max,
            },
            "task": None,
            "running": False,
            "sent": 0,
            "error": None,
        }
        self._tasks[sid] = entry
        try:
            self._validate(entry["config"])
        except ValueError:
            self._tasks.pop(sid)
            raise
        if auto_start:
            self.start(sid)
        return self._public(sid)

    def update(self, sid: str, **kw) -> dict:
        """在线修改任务参数，运行中下一周期生效。"""
        entry = self._get(sid)
        cfg = dict(entry["config"])
        if "data_list" in kw:
            cfg["data_list"] = kw["data_list"]
        for key in ("random_seed", "random_mask", "ramp_min", "ramp_max"):
            if key in kw:
                cfg[key] = kw[key]
        if kw.get("data"):
            cfg["data_hex"] = str(kw["data"]).replace(" ", "")
        if kw.get("data_hex"):
            cfg["data_hex"] = str(kw["data_hex"]).replace(" ", "")
        for key in ("name", "mode"):
            if kw.get(key):
                cfg[key] = kw[key]
        for key in ("arbitration_id", "period_ms", "inc_byte", "inc_step", "inc_end"):
            if kw.get(key) is not None:
                cfg[key] = int(kw[key])
        # 只改起始字节时自动抬高结束字节，避免 起>止
        if "inc_byte" in kw and "inc_end" not in kw and cfg["inc_end"] < cfg["inc_byte"]:
            cfg["inc_end"] = cfg["inc_byte"]
        if kw.get("is_extended_id") is not None:
            value = kw["is_extended_id"]
            if isinstance(value, str):
                value = value.strip().lower() not in {"false", "0", "no", "off", ""}
            cfg["is_extended_id"] = bool(value)
        self._validate(cfg)
        entry["config"] = cfg
        return self._public(sid)

    @staticmethod
    def _validate(cfg: dict) -> None:
        max_id = 0x1FFFFFFF if cfg["is_extended_id"] else 0x7FF
        if not 0 <= cfg["arbitration_id"] <= max_id:
            frame_type = "扩展帧" if cfg["is_extended_id"] else "标准帧"
            raise ValueError(f"{frame_type} ID 须为 0-{max_id:#x}")
        if cfg["period_ms"] <= 0:
            raise ValueError("周期必须为正数毫秒")
        data = bytes.fromhex(cfg["data_hex"])  # hex 校验
        if len(data) > 8:
            raise ValueError("CAN 数据长度不能超过 8 字节")
        if cfg["mode"] not in ("fixed", "increment", "list", "random", "ramp"):
            raise ValueError(f"模式须为 fixed/increment/list/random/ramp: {cfg['mode']}")
        for key in ("random_seed", "ramp_min", "ramp_max"):
            if type(cfg[key]) is not int:
                raise ValueError(f"{key} 必须为整数")
        if not isinstance(cfg["random_mask"], str):
            raise ValueError("随机掩码必须是十六进制字符串")
        mask = bytes.fromhex(cfg["random_mask"])
        if len(mask) > 8:
            raise ValueError("随机掩码不能超过 8 字节")
        cfg["random_mask"] = mask.hex().upper()
        if cfg["mode"] == "random" and mask and len(mask) != len(data):
            raise ValueError("随机掩码长度必须等于数据长度，或留空表示全部随机")
        sequence = cfg["data_list"]
        if not isinstance(sequence, list) or any(not isinstance(item, str) for item in sequence):
            raise ValueError("数据列表必须是十六进制字符串数组")
        normalized = []
        for item in sequence:
            payload = bytes.fromhex(item)
            if len(payload) > 8:
                raise ValueError("数据列表每项不能超过 8 字节")
            normalized.append(payload.hex().upper())
        if cfg["mode"] == "list" and not normalized:
            raise ValueError("列表模式至少需要一项数据")
        cfg["data_list"] = normalized
        if cfg["mode"] in ("increment", "ramp"):
            if not 0 <= cfg["inc_byte"] <= cfg["inc_end"] <= 7:
                raise ValueError("递增字节须满足 0 <= 起 <= 止 <= 7")
            if cfg["inc_end"] >= len(data):
                raise ValueError("递增结束字节不能超过数据长度")
            if cfg["inc_step"] == 0:
                raise ValueError("递增步长不能为 0")
            if cfg["mode"] == "ramp":
                limit = 1 << (8 * (cfg["inc_end"] - cfg["inc_byte"] + 1))
                if not 0 <= cfg["ramp_min"] <= cfg["ramp_max"] < limit:
                    raise ValueError("斜坡上下限必须在选中字节区间的无符号范围内，且下限不大于上限")

    def _current_data(self, cfg: dict, n: int) -> bytes:
        if cfg["mode"] == "list":
            sequence = cfg["data_list"]
            return bytes.fromhex(sequence[n % len(sequence)])
        data = bytearray(bytes.fromhex(cfg["data_hex"]))
        if cfg["mode"] == "random":
            rng = random.Random(f"{cfg['random_seed']}:{n}")
            mask = bytes.fromhex(cfg["random_mask"]) or bytes([255]) * len(data)
            return bytes((value & ~bits) | (rng.getrandbits(8) & bits)
                         for value, bits in zip(data, mask))
        if cfg["mode"] == "ramp":
            start, end = cfg["inc_byte"], cfg["inc_end"]
            low, high, step = cfg["ramp_min"], cfg["ramp_max"], cfg["inc_step"]
            # 超过边界后从起点重启；步长不能整除范围时不强插边界帧。
            offset = (n % ((high - low) // abs(step) + 1)) * abs(step)
            value = low + offset if step > 0 else high - offset
            data[start:end + 1] = value.to_bytes(end - start + 1, "little")
        if cfg["mode"] == "increment":
            start, end = cfg["inc_byte"], cfg["inc_end"]
            if 0 <= start <= end < len(data):
                width = end - start + 1
                span = 1 << (8 * width)
                val = int.from_bytes(data[start : end + 1], "little")  # J1939 小端
                val = (val + cfg["inc_step"] * n) % span
                data[start : end + 1] = val.to_bytes(width, "little")
        return bytes(data)

    def start(self, sid: str) -> dict:
        entry = self._get(sid)
        if not entry["running"]:
            entry["running"] = True
            entry["error"] = None
            entry["task"] = self._spawn(sid)
        return self._public(sid)

    def _spawn(self, sid: str):
        async def run() -> None:
            n = 0
            try:
                while self._tasks.get(sid, {}).get("running"):
                    cfg = self._tasks[sid]["config"]  # 每周期重读，支持在线修改
                    try:
                        self._bus.send(
                            cfg["arbitration_id"],
                            self._current_data(cfg, n),
                            cfg["is_extended_id"],
                        )
                        self._tasks[sid]["sent"] += 1
                        n += 1
                    except (RuntimeError, can.CanError) as e:
                        self._tasks[sid]["error"] = str(e)
                        self._tasks[sid]["running"] = False
                        break
                    await asyncio.sleep(cfg["period_ms"] / 1000)
            except asyncio.CancelledError:
                pass

        return asyncio.get_running_loop().create_task(run())

    def stop(self, sid: str) -> dict:
        entry = self._get(sid)
        if entry["running"]:
            entry["running"] = False
            if entry["task"]:
                entry["task"].cancel()
                entry["task"] = None
        return self._public(sid)

    def remove(self, sid: str) -> None:
        self.stop(sid)
        self._tasks.pop(sid, None)

    def duplicate(self, sid: str) -> dict:
        source = self._get(sid)["config"]
        return self.create(
            name=f"{source['name']}_副本",
            arbitration_id=source["arbitration_id"],
            data_hex=source["data_hex"],
            period_ms=source["period_ms"],
            is_extended_id=source["is_extended_id"],
            auto_start=False,
            mode=source["mode"],
            inc_byte=source["inc_byte"],
            inc_step=source["inc_step"],
            inc_end=source["inc_end"],
            data_list=source["data_list"],
            random_seed=source["random_seed"], random_mask=source["random_mask"],
            ramp_min=source["ramp_min"], ramp_max=source["ramp_max"],
        )

    def stop_all(self) -> None:
        for sid in list(self._tasks):
            self.stop(sid)

    def list(self) -> list[dict]:
        return [self._public(s) for s in self._tasks]

    # --------------------------------------------------------------- helpers
    def _get(self, sid: str) -> dict:
        if sid not in self._tasks:
            raise KeyError(f"任务不存在: {sid}")
        return self._tasks[sid]

    def _public(self, sid: str) -> dict:
        e = self._tasks[sid]
        return {**e["config"], "data_list": list(e["config"]["data_list"]),
                "running": e["running"], "sent": e["sent"], "error": e["error"]}
