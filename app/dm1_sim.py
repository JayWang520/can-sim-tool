"""发动机故障(DM1)模拟引擎。

按配置周期广播 DM1：DTC 数量决定单包（<=1 个 DTC，载荷 <= 8 字节）
或多包 TP.BAM（>=2 个 DTC）。SA 默认 0x00（模拟发动机 ECU）。
"""
from __future__ import annotations

import asyncio
from typing import Optional

import can

from . import j1939
from .bus import BusService

LAMP_STATES = {"off": j1939.LAMP_OFF, "on": j1939.LAMP_ON, "blink": j1939.LAMP_BLINK, "na": j1939.LAMP_NA}


def lamps_from_config(cfg: dict) -> bytes:
    return j1939.encode_lamps(
        mil=LAMP_STATES.get(cfg.get("mil", "off"), 0),
        red=LAMP_STATES.get(cfg.get("red", "off"), 0),
        amber=LAMP_STATES.get(cfg.get("amber", "off"), 0),
        protect=LAMP_STATES.get(cfg.get("protect", "off"), 0),
    )


class Dm1Sim:
    def __init__(self, bus: BusService) -> None:
        self._bus = bus
        self._task: Optional[asyncio.Task] = None
        self.config: dict = {
            "dtcs": [],  # [{spn, fmi, oc}]
            "lamps": {"mil": "off", "red": "off", "amber": "off", "protect": "off"},
            "sa": 0x00,
            "da": None,  # 目标地址：None=广播(PDU1 默认 FF)；仅 PDU1 格式 PGN 生效
            "priority": 6,
            "period_ms": 1000,  # SAE 推荐 DM1 1s 周期
            "pgn": j1939.PGN_DM1,  # 可自定义：DM2(65227)、私有 PGN 等
            "tp_cm_id": None,  # 多包通告帧完整 ID：None=跟随节点自动(标准 TP EC + 优先级 + SA)
            "tp_dt_id": None,  # 多包数据帧完整 ID：None=跟随节点自动(标准 TP ED + 优先级 + SA)
            "oc_auto_inc": False,  # 每周期 DTC 发生次数 +1（模拟故障持续发生），127 回绕
        }
        self.sent_frames = 0
        self.last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def update(self, cfg: dict) -> dict:
        """合并配置；运行中修改下一周期生效。

        支持直接给完整 29bit ID（arb_id），内部自动拆解为优先级/PGN/DA/SA。
        """
        cfg = dict(cfg)
        if cfg.get("arb_id") is not None:
            aid = int(cfg["arb_id"])
            if not 0 <= aid <= 0x1FFFFFFF:
                raise ValueError(f"ID 超出 29bit 范围: {hex(aid)}")
            info = j1939.decode_id(aid)
            self.config["priority"] = info["priority"]
            self.config["pgn"] = info["pgn"]
            self.config["sa"] = info["sa"]
            self.config["da"] = info["da"] if info["is_pdu1"] else None
            cfg.pop("arb_id")
        for key in ("dtcs", "lamps", "sa", "da", "priority", "period_ms", "pgn",
                    "tp_cm_id", "tp_dt_id", "oc_auto_inc"):
            if key in cfg:
                self.config[key] = cfg[key]
        if not 0 <= self.config["sa"] <= 255:
            raise ValueError(f"源地址 SA 须为 0-255，当前: {self.config['sa']}")
        if self.config["da"] is not None and not 0 <= self.config["da"] <= 255:
            raise ValueError(f"目标地址 DA 须为 0-255 或留空，当前: {self.config['da']}")
        for pk in ("pgn",):
            if not 0 <= self.config[pk] <= 0x3FFFF:
                raise ValueError(f"PGN 须为 0-0x3FFFF（{pk}），当前: {self.config[pk]}")
        for tk in ("tp_cm_id", "tp_dt_id"):
            if self.config[tk] is not None and not 0 <= self.config[tk] <= 0x1FFFFFFF:
                raise ValueError(f"ID 须为 0-0x1FFFFFFF（{tk}），当前: {hex(self.config[tk])}")
        if not 1 <= self.config["priority"] <= 7:
            raise ValueError(f"优先级须为 1-7，当前: {self.config['priority']}")
        if self.config["period_ms"] < 10:
            raise ValueError("周期最小 10ms")
        # 校验 DTC 字段
        for d in self.config["dtcs"]:
            j1939.DTC(spn=d["spn"], fmi=d["fmi"], oc=d.get("oc", 1))
        return self.status()

    def _effective_lamps(self) -> bytes:
        lamps = lamps_from_config(self.config["lamps"])
        if not self.config["dtcs"] and lamps == j1939.encode_lamps():
            return b"\xff\xff"  # 无故障且灯全灭 → 行业惯例发全 FF"无故障"帧
        return lamps

    def _build_frames(self) -> list[can.Message]:
        dtcs = [j1939.DTC(**d) for d in self.config["dtcs"]]
        return j1939.dm1_frames(
            dtcs, self._effective_lamps(),
            sa=self.config["sa"], priority=self.config["priority"],
            pgn=self.config["pgn"], da=self.config.get("da"),
            cm_id=self.config.get("tp_cm_id"),
            dt_id=self.config.get("tp_dt_id"),
        )

    def preview(self) -> dict:
        """预览 J1939 打包结果：模式 + 每一帧的 ID/数据/说明。"""
        payload = j1939.build_dm1_payload(
            [j1939.DTC(**d) for d in self.config["dtcs"]], self._effective_lamps()
        )
        frames = self._build_frames()
        if len(frames) == 1:
            descs = ["故障报文单帧"]
        else:
            descs = ["TP.CM BAM 通告"] + [f"TP.DT 数据包 #{i}" for i in range(1, len(frames))]
        return {
            "mode": "single" if len(frames) == 1 else "bam",
            "frame_count": len(frames),
            "payload_len": len(payload),
            "frames": [
                {
                    "id": f"{f.arbitration_id:08X}",
                    "data": bytes(f.data).hex().upper(),
                    "desc": desc,
                }
                for f, desc in zip(frames, descs)
            ],
        }

    def send_once(self) -> dict:
        """立即按当前配置打包并发送一组 DM1（不启动周期）。"""
        frames = self._build_frames()
        sent = 0
        try:
            for f in frames:
                self._bus.send(f.arbitration_id, bytes(f.data), True)
                self.sent_frames += 1
                sent += 1
        except RuntimeError as e:
            self.last_error = str(e)
            raise
        return {"sent": sent, "preview": self.preview()}

    def start(self) -> dict:
        if self.running:
            return self.status()
        self.last_error = None
        self._task = asyncio.get_running_loop().create_task(self._run())
        return self.status()

    def stop(self) -> dict:
        if self._task:
            self._task.cancel()
            self._task = None
        return self.status()

    async def _run(self) -> None:
        try:
            while True:
                try:
                    for f in self._build_frames():
                        self._bus.send(f.arbitration_id, bytes(f.data), True)
                        self.sent_frames += 1
                except RuntimeError as e:
                    self.last_error = str(e)
                    break
                if self.config.get("oc_auto_inc"):
                    for d in self.config["dtcs"]:
                        d["oc"] = (d.get("oc", 1) % 0x7F) + 1  # 7bit 回绕
                await asyncio.sleep(self.config["period_ms"] / 1000)
        except asyncio.CancelledError:
            pass

    def status(self) -> dict:
        return {
            "running": self.running,
            "config": self.config,
            "preview": self.preview(),
            "sent_frames": self.sent_frames,
            "last_error": self.last_error,
        }
